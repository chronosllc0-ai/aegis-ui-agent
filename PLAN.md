# Aegis → Always-On Runtime: Implementation Plan

> **Audience:** any engineer or AI agent picking this up mid-stream.
> This document is **the contract**. If you finish nothing else, keep this file accurate.
> **Branch:** `refactor/always-on-runtime` (cut from `origin/main` at `eee4348`).

---

## 0. North Star

Aegis today is a **vision-first browser navigator** with a chat skin bolted on top. It must become an **always-on AI coworker** (like OpenClaw / Claude Code background agents / Cursor background agents) where the browser is just **one tool among many**, not the runtime itself.

**Hard requirements from the product owner (Jesse):**

1. Always-on, server-resident runtime. Agent keeps working whether or not any browser tab is open.
2. Browser is a **tool**, not the execution system. Playwright + Browser MCP are exposed as *MCP tools* the agent selects per task.
3. No auto browser frames. Screenshots only when the model explicitly calls a browser screenshot tool, rendered inline in the chat thread on whatever surface the user is using.
4. All 40+ existing agent tools preserved.
5. Every connector and MCP server in the Connections tab must be **real** — zero stubs, zero hardcoded fixture manifests.
6. Multi-provider agent loop. Canonical SDK = **OpenAI Agents SDK** (`openai-agents` Python package). Other providers via provider shims / LiteLLM.
7. All connectors exposed as agent tools on day one: Notion, Linear, Google (Gmail, Calendar, Drive), GitHub, Slack.
8. Chat-only frontend for now. Browser panel is gone. When/if a browser panel returns it's a separate, opt-in surface.
9. Docs: delete the **standalone** docs site (`docs-site/`). Keep **embedded** docs (`frontend/src/public/docs/*` + `shared/docs/*`). Strip any internal / trade-secret detail from embedded docs.
10. Preserve Railway backend + Netlify frontend deployment shape. Do not re-introduce any browser hard-dependency at connect time.
11. **One main persistent session per user**, shared across *all* channels — web chat, Slack, Telegram, Discord, heartbeat triggers, subagent callbacks — all read and write the same conversation state. Channel-specific threads/DMs are subscribers/producers into the same session, not separate agents.
12. **Compaction checkpoints are preserved.** When the model hits the context limit, run the compaction flow (summarize history into a checkpoint, retain only the checkpoint + recent turns + pinned memories). This is a **must-keep** feature — it is how the session survives multi-day work.
13. **Context meter must account for the full loaded context, not just visible chat.** That means: system prompt, active skills section, loaded workspace files (e.g. `HEARTBEAT.md`, `AGENTS.md`, any file the agent has opened), background instructions (heartbeat prompt, pending automations, pinned memories), plus visible chat history. The UI meter must reflect the *real* token footprint — users should never be surprised by a compaction because the meter lied about how full the window was.

**Non-negotiable: no regressions in the 40+ tool set.** If a tool is removed, it is replaced by an equivalent or better one and PLAN.md is updated.

---

## 1. Current State (evidence — do not re-investigate from scratch)

### 1.1 The websocket is browser-tethered at connect

`main.py`, WebSocket handler (~line 2885):

```python
try:
    _get_orchestrator()
    await _send_initial_frame(websocket)

    while True:
        data = await websocket.receive_json()
        ...
```

`_send_initial_frame` (`main.py` ~line 2080) calls `executor.screenshot()` → `ActionExecutor.ensure_browser()` → `playwright.chromium.launch(...)`. If Chromium isn't healthy (Railway image, first-connect cold start, any Playwright install drift), the connection stalls *before* the agent can receive a single user message. The Codex review in PR #332 explicitly flagged this: removing `_send_initial_frame` breaks an implicit handshake because senders wait for the first frame before emitting `navigate_start`.

Every inbound action on the websocket is normalized to `navigate_start` (`main.py` ~line 2754):

```python
if action in {"navigate", "task", "chat", "message"}:
    action = "navigate_start"
```

There is a **single** code path for chat, task, and navigation. That single path is browser-first.

### 1.2 Heartbeat requires a live websocket

`backend/heartbeat_pinger.py` + `backend/heartbeat_session.py` fire `dispatch(session_id, instruction)` on cron. `dispatch` points at `_heartbeat_dispatch` in `main.py` (~line 583):

```python
if runtime is None or runtime.websocket is None:
    logger.info("Heartbeat dispatch (no active runtime): ...")
    return
```

Close the tab → heartbeat silently returns. The entire `SessionRuntime` dataclass ties steering, user-input futures, task cancellation, and subagent management to `websocket.send_json(...)`. There is no server-owned runtime that can act without a connected client.

### 1.3 Browser is the agent, not a tool

`orchestrator.py::AgentOrchestrator._build_agent(...)` wires the Gemini ADK agent with a hard-coded browser toolbelt: `take_screenshot, click_element, type_text, scroll_page, go_to_url, wait_for_load, go_back`. These are first-class tools.

The websocket also exposes **direct browser control** as first-class message types:

```python
# main.py ~line 3335+
action == "click"      → await _get_orchestrator().executor.click(x, y)
action == "type_text"  → await _get_orchestrator().executor.type_text(...)
action == "scroll"     → await _get_orchestrator().executor.scroll(...)
action == "press_key"  → await _get_orchestrator().executor.press_key(...)
```

This is a **remote-control protocol for a browser**, not a chat protocol.

Frame fan-out: `_on_frame_combined` auto-forwards browser frames to Telegram / Discord subscribers on a ~3s cadence, regardless of whether the agent actually did anything.

### 1.4 MCP and connectors are half-stubs

`backend/mcp/transport.py::scan_mcp_tools` returns **hardcoded fixture manifests**:

```python
if preset == "preset-browsermcp":
    tools = [
        {"name": "browser_navigate", ...},
        {"name": "browser_click", ...},
        {"name": "browser_screenshot", ...},
    ]
```

No MCP handshake. No tool/list. No stdio spawn. No http/sse client. `mcp_client.py::MCPClient` is custom, not the official `modelcontextprotocol` SDK.

`backend/connectors/*` (`notion_connector.py`, `linear_connector.py`, `google_connector.py`, `slack_connector.py`, `github_connector.py`) *are* real: OAuth flows work, `execute_action(action_id, params, access_token)` hits real provider APIs (Notion `/search`, Linear GraphQL, Google APIs). But they are exposed **only** at `/api/connectors/*` HTTP routes. The agent's tool list (`TOOL_DEFINITIONS` in `universal_navigator.py` line 188) does **not** include `notion_*`, `linear_*`, `google_*`, `gmail_*`, `calendar_*`, or `drive_*` tools. The Connections tab looks like a marketplace, but the agent cannot use most of it.

### 1.5 Frontend has two docs surfaces

- **Standalone docs site:** `docs-site/` (separate Vite app, reads from `shared/docs/*` + `shared/docs-ui/*`). **DELETE.**
- **Embedded docs:** `frontend/src/public/docs/*` + `frontend/src/public/EmbeddedDocsPage.tsx` (consumes same `shared/docs/content.ts`). **KEEP.** Strip trade-secret details.
- `frontend/public/docs.html` is a public-site marketing stub. Keep if it just links to embedded docs; delete if it deep-links to the standalone site.

### 1.6 Tool registry inventory (50 entries in `TOOL_DEFINITIONS`)

| Category | Tools |
|---|---|
| Browser | `screenshot`, `go_to_url`, `click`, `type_text`, `scroll`, `go_back`, `wait` |
| Web / extraction | `web_search`, `extract_page` |
| Workspace files | `list_files`, `read_file`, `write_file` |
| Code exec | `exec_python`, `exec_javascript`, `exec_shell` |
| Flow control | `ask_user_input`, `handoff_to_user`, `summarize_task`, `confirm_plan`, `done`, `error` |
| Memory (v2) | `memory_search`, `memory_write`, `memory_read`, `memory_patch` |
| Memory (legacy) | `read_memory`, `write_memory`, `patch_memory`, `compact_memory` |
| Cron | `cron_write`, `cron_patch`, `cron_delete` |
| Automations | `add_automation`, `list_automations`, `remove_automation` |
| Subagents | `spawn_subagent`, `message_subagent`, `steer_subagent` |
| GitHub | `github_list_repos`, `github_get_issues`, `github_create_issue`, `github_get_pull_requests`, `github_create_comment`, `github_get_file`, `github_clone_repo`, `github_create_branch`, `github_repo_status`, `github_repo_diff`, `github_commit_changes`, `github_push_branch`, `github_create_pull_request` |

All 43 non-terminal tools must survive migration. The browser tools (7) become thin wrappers over the Playwright MCP tool calls. Everything else moves behind the Agents SDK `@function_tool` decorator.

---

## 2. Target Architecture

```
Client surfaces           Ingress              Task bus                 Runtime                    Tools / Egress
─────────────────        ─────────            ─────────                ───────────                ─────────────
Web chat (chat-only) ─┐  Chat API     ──┐    per-user priority     Session Supervisor    ──┬─→  Native tools
Slack bot            ─┤  (REST+WS stream) │  queue                 (owned by user uid,     │   (40+ existing)
Telegram bot         ─┤                   │                        survives tab close)     │
Discord bot          ─┼─>                ─┼─> Router ─────────→    │                       ├─→  MCP Host
Webhooks (GitHub,    ─┤  Webhook API  ──┘   (owner resolver)       Agent Loop              │   (official mcp SDK:
 Stripe, etc.)       ─┤                                            (OpenAI Agents SDK,     │    Playwright MCP,
Heartbeat cron       ─┤                                             multi-provider via     │    Browser MCP,
User automations     ─┘                                             LiteLLM)               │    user-installed)
                                                                    │                       │
                                                                    Memory + Skills +       ├─→  OAuth connectors
                                                                    Workspace FS            │   (Notion, Linear,
                                                                                            │    Google, GitHub,
                                                                                            │    Slack exposed
                                                                                            │    as tools)
                                                                                            └─→  Renderer →
                                                                                                 Channel-aware egress
                                                                                                 (text + screenshots
                                                                                                  + files to the
                                                                                                  surface that
                                                                                                  triggered the run)

Persistence: Postgres (sessions, messages, runs, memories, connectors) + workspace FS.
```

### 2.0 Session model (critical — read first)

- **One persistent session per user, shared across channels.** The server-owned runtime is keyed by `owner_uid` (user account), not by `(user, channel)`. Every inbound event — web chat, Slack DM/mention, Telegram message, Discord message, heartbeat tick, webhook payload, automation fire, subagent callback — lands as an `AgentEvent` on the **same** `SessionSupervisor.inbox` for that user. The agent reads from the same conversation state regardless of surface.
- Channels are **subscribers + producers**: they emit events into the supervisor and render outputs back to whichever surface(s) subscribed. The "Subscribe Slack thread to session X" action is first-class.
- Subagents are **child supervisors with a linked inbox** into the parent session. `spawn_subagent(...)` creates a child run whose output events are forwarded into the parent's conversation as agent-sourced messages. No out-of-band state.
- Heartbeat fires as `AgentEvent(HEARTBEAT)` with a well-known prompt pulled from `HEARTBEAT.md`. If a heartbeat arrives while the session is busy, it is queued per the priority ladder (user_chat > webhook > heartbeat > background).

### 2.1 Context window management (critical — read second)

- **Compaction checkpoints are preserved.** When a turn's projected token count would exceed the model's context window (minus a configurable headroom), the runtime runs the existing `compact_memory` flow: summarize history up to the last checkpoint, insert a `CHECKPOINT: <summary>` block, drop the compacted turns, keep the most recent `N` turns + pinned memories + the checkpoint. This is a **must-keep** capability — removing it regresses multi-day sessions.
- Compaction is triggered **proactively** at ≥ 90% of the window (configurable `COMPACT_THRESHOLD_PCT`), not reactively on overflow error.
- **The context meter in the UI reflects the real loaded footprint,** not just visible chat tokens. It must sum, at minimum:
  1. System prompt (identity + rules + tool catalog)
  2. Active runtime skills block (what `universal_navigator.py::_assemble_runtime_skills_section` currently produces)
  3. Loaded workspace files (e.g. `HEARTBEAT.md`, `AGENTS.md`, any file the agent has `read_file`'d this session)
  4. Pinned memories / connector state blobs that will be injected into the next prompt
  5. Pending tool outputs still in the scratch buffer
  6. Visible chat history tokens
- Backend exposes this via `GET /api/runtime/context-meter/{session_id}` returning a JSON breakdown by bucket. Frontend renders the breakdown on hover so the user understands *why* the meter is where it is.
- Update the meter on every event that changes the loaded context: tool call result, skill activation, workspace file read, memory write, compaction event.

### 2.2 Core moves

1. **Decouple runtime from websocket.** A `SessionSupervisor` (name: `backend/runtime/supervisor.py`) owns state per user uid. Websockets become *event producers* — they push messages into the supervisor's queue and subscribe to outputs. If the websocket disconnects, the supervisor keeps running.
2. **Single event bus.** Chat messages (any surface), cron heartbeat, webhooks, automations, and agent→agent messages all land as `AgentEvent` objects on `supervisor.inbox`. Priorities: `user_chat > webhook > heartbeat > background`.
3. **Agents SDK as canonical loop.** Use `openai-agents` Python package. One `Agent` per session, `runner.run_streamed(...)`. Multi-provider via `openai.AsyncClient` pointed at LiteLLM gateway (or `openrouter.ai/api/v1`).
4. **Real MCP host.** Adopt `modelcontextprotocol.sdk` Python package (`pip install mcp`). Spawn stdio MCPs, connect to http/sse MCPs, run `tools/list`, expose as Agents SDK tools. Day-one MCP servers:
   - `@playwright/mcp` (Microsoft, stdio) — server-side browser. Replaces the current `executor.py` entirely.
   - `@browsermcp/mcp` — user-browser MCP. Current `preset-browsermcp` card must become a real install, not a hardcoded fixture.
   - Any user-added MCP from the Connections tab.
5. **Connectors-as-tools.** Auto-generate Agents SDK function tools from each `ConnectorAction` returned by `backend/connectors/*::list_actions()`. Tool name: `{connector_id}_{action_id}`. Tool invocation: resolve per-user OAuth token, call `connector.execute_action(...)`.
6. **Browser tools become MCP calls.** The 7 browser entries in `TOOL_DEFINITIONS` stay in the agent's visible manifest, but are implemented as thin shims over Playwright MCP or Browser MCP (user-selectable per task via settings).
7. **Remove auto-frames and direct browser control.**
   - Delete `_send_initial_frame` and the receive-loop call.
   - Delete the `click / type_text / scroll / press_key` websocket action handlers.
   - Delete the 3s `_on_frame_combined` Telegram / Discord frame forwarder.
   - `screenshot` tool returns bytes; renderer attaches as an image message on whatever surface the caller is on.
8. **Chat-only frontend shell.** Remove `ScreenView`, `ActionLog` (browser-primitives), and any component that assumes a live frame. The "Request web screenshot" CTA from PR #322 is enough.
9. **Persistence.** Every user message, agent turn, tool call, tool result, memory, connector token, and task state rides in Postgres. Use the existing `backend/database.py` async session factory. Add Alembic-style migrations via raw SQL in `backend/migrations/` (no Alembic dependency yet if it's not already present — check before adding).
10. **Docs:** remove `docs-site/` directory and every reference to it. Strip `shared/docs/content.ts` of internal implementation detail. Embedded docs stay, rewritten for public consumption.

### 2.3 What the agent loop looks like

```python
# backend/runtime/agent_loop.py  (new)
from agents import Agent, Runner, function_tool, RunContextWrapper
from backend.runtime.tools.native import NATIVE_TOOLS
from backend.runtime.tools.mcp_host import MCPToolProvider
from backend.runtime.tools.connectors import ConnectorToolProvider

async def build_agent(session_id: str, user_uid: str, settings: dict) -> Agent:
    tools = []
    tools.extend(NATIVE_TOOLS)
    tools.extend(await MCPToolProvider(user_uid=user_uid).resolve())
    tools.extend(await ConnectorToolProvider(user_uid=user_uid).resolve())
    return Agent(
        name="Aegis",
        instructions=await build_system_prompt(session_id, user_uid, settings),
        tools=tools,
        model=settings.get("model") or "gpt-4o",  # or LiteLLM route
    )
```

The `SessionSupervisor` owns a streaming loop:

```python
async def run(self):
    async for event in self.inbox:
        agent = await build_agent(self.session_id, self.user_uid, self.settings)
        result = Runner.run_streamed(agent, event.prompt, context=self.context())
        async for step in result.stream_events():
            await self.fanout(step)
```

No websocket. `self.fanout(step)` pushes to whatever surfaces are subscribed (web chat subscribers list, Slack thread, Telegram chat id, Discord channel id).

### 2.4 What the MCP host looks like

```python
# backend/runtime/tools/mcp_host.py  (new)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

class MCPToolProvider:
    async def resolve(self) -> list[FunctionTool]:
        server_configs = await load_user_mcp_servers(self.user_uid)
        tools: list[FunctionTool] = []
        for cfg in server_configs:
            session = await self._connect(cfg)
            listed = await session.list_tools()
            for t in listed.tools:
                tools.append(self._wrap(session, t, namespace=cfg.name))
        return tools
```

The `scan_mcp_tools` fixture in `backend/mcp/transport.py` gets deleted. The Connections tab's "Scan tools" action calls the real provider.

### 2.5 What the Connectors-as-tools layer looks like

```python
# backend/runtime/tools/connectors.py  (new)
from backend.connectors import CONNECTOR_REGISTRY

class ConnectorToolProvider:
    async def resolve(self) -> list[FunctionTool]:
        tools: list[FunctionTool] = []
        for cid, connector in CONNECTOR_REGISTRY.items():
            user_token = await get_user_connector_token(self.user_uid, cid)
            if not user_token:
                continue
            for action in connector.list_actions():
                tools.append(self._wrap(connector, action, token=user_token))
        return tools
```

Each connector already returns `list_actions() → list[ConnectorAction]`. We just convert those to Agents SDK `@function_tool` definitions and call `connector.execute_action(action.id, params, token)` inside.

---

## 3. File-by-file change catalog

### 3.1 Create (new)

| Path | Purpose |
|---|---|
| `backend/runtime/__init__.py` | Package marker. |
| `backend/runtime/supervisor.py` | `SessionSupervisor` — per-user always-on runtime. |
| `backend/runtime/events.py` | `AgentEvent` dataclass + priority enum + inbox queue. |
| `backend/runtime/agent_loop.py` | Builds Agents SDK `Agent` per turn; runs `Runner.run_streamed`. |
| `backend/runtime/fanout.py` | Subscriber fan-out (web, slack, telegram, discord, webhook reply). |
| `backend/runtime/persistence.py` | Postgres read/write for runs, messages, tool calls, task state. |
| `backend/runtime/tools/__init__.py` | Tool aggregation entry point. |
| `backend/runtime/tools/native.py` | Agents SDK wrappers for all existing 40+ native tools. |
| `backend/runtime/tools/mcp_host.py` | Real MCP host using `mcp` SDK. |
| `backend/runtime/tools/connectors.py` | Connector→tool auto-wrapper. |
| `backend/runtime/tools/browser.py` | `screenshot`/`go_to_url`/... shims delegating to Playwright MCP or Browser MCP. |
| `backend/runtime/providers.py` | Multi-provider shim (OpenAI + LiteLLM + provider-native where needed). |
| `backend/ingress/chat.py` | Chat REST + WS stream gateway (replaces the monolithic `main.py` websocket handler). |
| `backend/ingress/webhooks.py` | Inbound webhook gateway. |
| `backend/ingress/heartbeat.py` | Heartbeat producer (was `backend/heartbeat_pinger.py`, now emits `AgentEvent`s). |
| `backend/migrations/202604XX_runtime_tables.sql` | Tables: `runs`, `run_events`, `tool_calls`, `runtime_subscribers`. |

### 3.2 Modify

| Path | Change |
|---|---|
| `main.py` | **Massive cleanup.** Remove `_send_initial_frame`, `_on_frame_combined`, browser-control websocket actions (`click`, `type_text`, `scroll`, `press_key`), and the single-path action normalization. Delegate chat/task to `backend.ingress.chat`. Keep startup + HTTP routers + auth. |
| `universal_navigator.py` | Either delete entirely (preferred) once `backend/runtime/agent_loop.py` is wired, or trim to a bridging shim for a short cutover window. Target: delete. |
| `orchestrator.py` | Delete `AgentOrchestrator`. Its responsibilities move into `backend/runtime/agent_loop.py` + `backend/runtime/tools/*`. |
| `executor.py` | Delete. Playwright MCP replaces it. |
| `analyzer.py` | Keep only if still used by remaining code; otherwise delete. |
| `backend/heartbeat_session.py` | Replace `dispatch` with `supervisor.inbox.put(AgentEvent(...))`. No more `runtime.websocket` check. |
| `backend/heartbeat_pinger.py` | Same: fire into the supervisor inbox. |
| `backend/mcp/transport.py` | **Delete `scan_mcp_tools` stub entirely.** Replace with `backend/runtime/tools/mcp_host.py::scan`. |
| `mcp_client.py` | Delete. Replaced by official `mcp` SDK. |
| `backend/connections/service.py` | `DEFAULT_MCP_PRESETS` must point to **real** MCP servers. BrowserMCP entry must install `@browsermcp/mcp` (npm) or a dockerized equivalent and return real tools. |
| `backend/connectors/router.py` | Keep HTTP surface for OAuth flows. Remove any action-execution route that is now accessible only via agent tool (unless also needed for the UI). |
| `frontend/src/App.tsx` | Remove `ScreenView`, `ActionLog`-browser-primitives, frame-handling state. |
| `frontend/src/components/ScreenView.tsx` | Delete. |
| `frontend/src/components/ActionLog.tsx` | Trim to text log only (no frames). Or delete and replace with chat-embedded tool-output blocks. |
| `frontend/src/hooks/useWebSocket.ts` | Remove frame subscription, remove browser-control action senders. |
| `frontend/src/lib/mcp.ts` | `DEFAULT_INTEGRATIONS` must match the real set: everything in `backend/connectors/` plus web-search / filesystem / code-exec / browser-mcp / playwright-mcp. |
| `frontend/src/components/settings/ConnectionsTab.tsx` | Wire "Scan tools" to the new real MCP scan endpoint. Remove any facade behavior. |
| `README.md` | Rewrite. Include the new architecture Mermaid diagram. Remove any detail that leaks internal implementation. |
| `ONBOARDING.md` | Update Session ≥ 7 notes: the runtime rewrite. Keep internal-only. |
| `AGENTS.md` | Update to reflect new module layout and the fact that the browser is a tool. |
| `shared/docs/content.ts` | Rewrite for public consumption. No `executor.py`, no `orchestrator.py`, no Playwright-internal references. Keep Quickstart, Auth, Provider keys, Connections, Automations, API reference (public endpoints only), FAQ, Changelog. |

### 3.3 Delete

| Path | Why |
|---|---|
| `docs-site/` (entire directory) | Standalone docs site is cut per owner direction. |
| `frontend/public/docs.html` | Only if it deep-links to the standalone site; otherwise redirect to embedded docs route. |
| `shared/docs-ui/` | Duplicated by `frontend/src/public/docs/*`. Keep one copy; prefer the embedded one. |
| `backend/mcp/transport.py::scan_mcp_tools` | Hardcoded fixture. |
| `mcp_client.py` | Custom MCP client replaced by official SDK. |
| `executor.py` | Playwright MCP replaces it. |
| `orchestrator.py` | Replaced by `backend/runtime/agent_loop.py`. |
| `universal_navigator.py` | Replaced by Agents SDK Runner + `backend/runtime/tools/*`. |
| `analyzer.py` | If unused after the above deletions. |
| `docs/codex-phase*.md`, `docs/admin-system-plan.md`, `docs/prompts/execution-agent-system-prompt.md`, `docs/skills-*.md`, `docs/thread-ux-fix-prompts.md`, `docs/fix-prompts-sequential.md` | Internal plans that leak architecture. Move to `docs/archive/` (already present) or delete outright. None of these ship to users. |

### 3.4 Keep untouched (reuse as-is)

- `backend/connectors/*.py` — real OAuth connectors. Only change: expose via new tool wrapper.
- `backend/memory/*` — memory service is already fine.
- `backend/skills/*` — runtime skills system stays.
- `backend/providers/*` — provider wrappers remain useful as LiteLLM fallback.
- `backend/session_workspace.py` — workspace file tree contract stays (`HEARTBEAT.md`, `AGENTS.md`, scratch).
- All tests in `tests/` — rewrite per phase but the matrix stays.

---

## 4. Phased migration plan

Each phase is a PR. Do not batch phases — this codebase has a lot of moving parts and review load matters.

### Phase 0 — Handoff artifact (this PR)

- [x] `PLAN.md` (this file)
- [ ] `README.md` rewritten with new architecture + Mermaid diagram
- [ ] `docs/architecture/always-on.mmd` (mermaid source, canonical)
- [ ] `docs/architecture/always-on.png` (rendered preview for GitHub)
- [ ] `docs-site/` deletion
- [ ] Embedded docs scrub checklist in `shared/docs/content.ts` (content changes shipped in Phase 5 — this PR only marks the TODO blocks)

**Merge criteria:** plan reviewed and accepted. No runtime changes.

### Phase 1 — Runtime decoupling scaffold (no behavior change yet)

- Add `backend/runtime/{supervisor.py, events.py, fanout.py, persistence.py, agent_loop.py}`.
- Supervisor is instantiated at app startup per user on first-message; survives websocket disconnect.
- Heartbeat pinger still works (now fires `AgentEvent(HEARTBEAT)` into the supervisor inbox) but initial agent wiring is empty — supervisor just logs.
- Add migrations for `runs`, `run_events`, `tool_calls`.
- Feature flag `RUNTIME_SUPERVISOR_ENABLED=false` so prod stays on the old path.

**Merge criteria:** tests pass, old path unaffected.

### Phase 2 — OpenAI Agents SDK loop + native tool port

- Install `openai-agents`, `litellm`.
- Build `backend/runtime/tools/native.py` wrapping all 43 non-terminal existing tools as `@function_tool`.
- Wire `backend/runtime/agent_loop.py::build_agent` + `SessionSupervisor.run()`.
- Under flag `RUNTIME_SUPERVISOR_ENABLED=true`, route chat messages through the new loop. Keep old Gemini path as fallback behind flag `LEGACY_ORCHESTRATOR=true`.
- Add `tests/test_runtime_supervisor_smoke.py` exercising: user message → agent turn → tool call → final message → persistence write → fan-out to a test subscriber.

**Merge criteria:** smoke test passes. `RUNTIME_SUPERVISOR_ENABLED=true` works end-to-end in a dev environment with at least one native tool exercised.

### Phase 3 — Real MCP host + Playwright MCP + fix Browser MCP

- Install `mcp` (the official Python SDK).
- Implement `backend/runtime/tools/mcp_host.py` with stdio + http + sse clients.
- Ship Playwright MCP (`@playwright/mcp`) as a default-on server — spawn stdio subprocess, `tools/list`, wrap tools.
- **Fix Browser MCP.** The `preset-browsermcp` card currently points at `http://localhost:3333/mcp` with no server running and hardcoded fixtures. Options (pick one; document the pick here once decided):
  - (a) Bundle `@browsermcp/mcp` as a user-side install guide + a backend-side stdio spawn when the user opts in.
  - (b) If Browser MCP must run in the user's browser (as the project intends), document the extension install flow + pairing endpoint, and have the backend proxy.
  - **Decision (Phase 3 PR):** Ship option **(a)**. `@browsermcp/mcp` is spawned as an **opt-in stdio subprocess on the backend**, gated by `BROWSERMCP_ENABLED=true` (with an optional `BROWSERMCP_COMMAND` override for bundled builds). The `preset-browsermcp` card now advertises the real `stdio` transport + `npx -y @browsermcp/mcp@latest` command instead of the dead `http://localhost:3333/mcp` URL. Option (b) is deferred until a future phase brings the browser extension + pairing UX.
- Delete `backend/mcp/transport.py::scan_mcp_tools` (the `test_mcp_transport` validator survives for the admin connection wizard). `/api/connections/mcp/servers/{id}/scan` now calls `backend.runtime.tools.mcp_host.scan_mcp_server` (via `scan_tools_for_server`) which opens a real MCP session, lists tools, and tears down.
- Delete `mcp_client.py`.

**Merge criteria:** fresh user with Playwright MCP enabled can run `go_to_url("https://example.com")` + `screenshot()` via the agent and see the image render in the chat surface. Browser MCP card flips from "preset" to "real" with a live `tools/list`.

### Phase 4 — Connectors-as-tools ✅ (PR #338)

- [x] Implement `backend/runtime/tools/connectors.py` — tool builder, tool-name canonicalisation (`{connector_id}_{action_id}`), per-call token decrypt + refresh-on-expiry, friendly `ERROR: …` surfacing.
- [x] Wire into `backend/runtime/agent_loop.py` — new `DispatchConfig.connector_loader` (defaults to `load_connector_tools`); appended after native + MCP tools so connector names never collide.
- [x] Expose 37 tools across the 5 OAuth connectors: Notion (6) · GitHub (9) · Google Gmail/Drive/Calendar (9) · Linear (7) · Slack (6).
- [x] `tests/test_runtime_connectors.py` — 12 tests covering name builder, schema translation, per-connector tool coverage, DB-backed discovery (active vs. revoked connections), decrypt + execute, no-connection error path, refresh-on-expiry with writeback, exception surfacing, JSON-arg validation.
- [ ] Per-connector conformance tests hitting sandbox tokens (skipped by default — follow-up).

**Merge criteria:** with Notion + Gmail + Linear + Slack + GitHub all connected, the agent can execute at least one non-trivial action per connector end-to-end (e.g. create a Notion page with content, send a Gmail draft, list Linear issues, post to a Slack channel, open a GitHub issue).

### Phase 5 — Frontend chat-only finalization

- Remove `ScreenView`, `ActionLog`-browser-primitives, frame subscriptions, browser-control hooks.
- Remove the standalone `docs-site/` (or it was removed in Phase 0 depending on batching).
- Scrub `shared/docs/content.ts` — replace internal references with generic descriptions.
- Make sure `EmbeddedDocsPage` renders fine without the "Open standalone docs" affordance.

**Merge criteria:** `npm run build` clean in `frontend/`, UI regression tests updated, Netlify preview renders.

### Phase 6 — Remove legacy paths + cleanup — **DONE (PR pending merge)**

- ✅ Deleted `universal_navigator.py` (2,750 LOC), `orchestrator.py` (408), `analyzer.py` (154), `executor.py` (113), `navigator.py` (70).
- ✅ Deleted `_get_orchestrator`, `_send_frame`, `_send_initial_frame`, `_on_frame_combined`, `_start_legacy_navigation_task`, `_run_navigation_task`, `_on_frame_for_stream`, `_run_navigation_task_from_bot` (~750 LOC across 8 helpers in `main.py`).
- ✅ Removed the `human_browser_action` + `handoff_continue` websocket handlers (now return `E_UNSUPPORTED_ACTION`).
- ✅ Removed `SessionRuntime.handoff_*` state + `clear_handoff_state`.
- ✅ Flipped `runtime_supervisor_enabled()` default `False → True`; dropped `legacy_orchestrator_enabled()` + the `LEGACY_ORCHESTRATOR` env var entirely.
- ✅ Rewrote `_start_navigation_task` to dispatch **only** through the supervisor; rewrote `_run_or_queue_from_bot_command` to enqueue `CHAT_MESSAGE` events for platform channels.
- ✅ Deleted 12 legacy tests (`test_analyzer`, `test_executor`, `test_orchestrator_*`, `test_parallel_tool_calls`, `test_universal_memory_mode`, `test_universal_navigator_*`, `test_conversation_persistence`, `test_main_websocket`).
- ✅ Updated `ONBOARDING.md` with Session ≥ 7 notes + `AGENTS.md` with the new module layout.

**Merge criteria:** no remaining import from the deleted modules. `grep -rn 'executor\|orchestrator\|navigator\|_send_initial_frame'` returns only historical log lines. Deploy to Railway + Netlify and verify heartbeat fires with no browser tab open.

### Phase 7 — Hardening — **IN PROGRESS (PR pending merge)**

**Shipped in this PR:**

- ✅ Inbox event durability — every `AgentEvent` accepted by
  `SessionSupervisor.enqueue` is persisted to the new
  `runtime_inbox_events` table *before* the worker picks it up. Table
  tracks full lifecycle: `pending → dispatched → completed | error |
  interrupted`, `run_id`, `dispatched_at`, `completed_at`, `error`.
- ✅ Tool-call checkpoints — new `runtime_tool_calls` table. The
  dispatch hook records a `started` row per `tool_call_item` and closes
  it out on the matching `tool_call_output_item`. On restart, rows
  still in `started` for an interrupted run are cascaded to
  `interrupted`.
- ✅ Boot rehydration — `backend/runtime/rehydration.py`
  (`rehydrate_pending_events`) runs at supervisor startup via
  `ensure_runtime_started()`. Rows in `pending` are rebuilt into
  `AgentEvent`s and re-enqueued; rows in `dispatched` become
  `interrupted` and get a `run_interrupted` fan-out frame for the UI.
- ✅ Sandbox prereq — `bubblewrap` added to the Railway Dockerfile so
  `run_code` has its sandbox binary available when the UI reintroduces
  it.

**Deferred to a follow-up phase:**

- [ ] Richer tool-call timings in `runtime_event_store` (current
      telemetry stays unchanged; this phase only adds the persistence
      ledger).
- [ ] Rate limits + credit accounting parity check against the new
      tool-call ledger.
- [ ] Security review: any new tool that touches `exec_shell` /
      `exec_python` / the filesystem must go through the existing
      sandbox.

**Merge criteria:** kill backend mid-tool-call, restart, agent picks
up at next event without losing session context. Verified end-to-end
in `tests/test_runtime_persistence.py` — `test_rehydration_marks_dispatched_row_interrupted`
plants a live `runtime_runs` + `runtime_tool_calls` + dispatched
`runtime_inbox_events` state and asserts the rehydration pass
transitions all three to `interrupted` and publishes a
`run_interrupted` fan-out frame; `test_rehydration_replays_pending_event`
re-enqueues a dropped message and watches it finish cleanly on a
fresh supervisor.

---

## 5. Decisions locked by the product owner

| Decision | Locked value |
|---|---|
| Agent loop SDK | **OpenAI Agents SDK** (`openai-agents`) with multi-provider via LiteLLM / provider shims. |
| Browser MCP posture | **Keep both** Playwright MCP + Browser MCP. Browser MCP implementation is incomplete today — fix it as part of Phase 3. |
| Connectors day-one scope | **All of them:** Notion, Linear, Google (Gmail + Calendar + Drive), GitHub, Slack. |
| Workspace FS behavior | **Unchanged.** Session workspace tree, `HEARTBEAT.md`, `AGENTS.md`, scratch files all stay. |
| Docs strategy | **Delete standalone `docs-site/`. Keep embedded docs under `frontend/src/public/docs/*`.** Strip internal / trade-secret detail from embedded docs. |

---

## 6. How an agent should pick this up mid-stream

If you are reading this because the previous agent ran out of credits or time, do this:

1. `git fetch origin && git checkout refactor/always-on-runtime`.
2. Read this file top to bottom.
3. `grep -n "- \[ \]" PLAN.md` to find open checkboxes under the current phase section.
4. Check `git log --oneline` on the branch vs. the Phase table in §4 to figure out which phase you're in.
5. Implement the next open phase. **One phase = one PR.** Do not batch.
6. Keep evidence in PR descriptions — quote exact file paths and line numbers when claiming something is fixed.
7. After finishing a phase, update PLAN.md: check off completed items, lock in any decisions that were made during implementation (e.g. "picked option (a) for Browser MCP because …").
8. If you deviate from the plan, write *why* in PLAN.md under a new "§8 Deviations" section.

Owner preferences you must respect:
- **No guessing.** If you're uncertain, grep the repo, read the code, or ask.
- **No placeholder stubs shipping to prod.** If a feature isn't ready, gate it behind a flag that defaults off.
- **No trade-secret leakage.** Internal architecture details do not go into `shared/docs/content.ts`, README, or any frontend-visible string.
- **Tool parity.** Every existing tool must still exist (or be explicitly replaced and logged here).
- **Railway (backend) + Netlify (frontend)** deployment shape stays. DB is Postgres over the Railway TCP proxy (`monorail.proxy.rlwy.net:44530`) — don't rewrite connection logic.

---

## 7. Open questions (resolve as work proceeds)

- **Browser MCP implementation path** — pick one of the two options in §4 Phase 3 and record choice.
- **LiteLLM vs. native provider SDKs** — default: LiteLLM as a thin gateway, native fallbacks only where a provider feature (reasoning traces, audio, vision) requires the native SDK.
- **Alembic vs. raw SQL migrations** — check `backend/migrations/` first; if Alembic is already present, use it.
- **Tool-name namespacing for MCP** — proposed: `{server_id}__{tool_name}` with double underscore. Lock once Phase 3 ships.
- **Subagent system** — `spawn_subagent` / `message_subagent` / `steer_subagent` currently assume in-process. With the supervisor model, subagents become child supervisors. Confirm the shape before Phase 2 rewrites those tools.

---

## 8. Deviations (append-only)

_Fill in as deviations occur._
