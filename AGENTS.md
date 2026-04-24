# AGENTS.md — Aegis AI Coworker

> Primary operating guide for coding agents working in this repository.

## Project Identity

**Name:** Aegis  
**Tagline:** Always-on AI coworker agent  
**Positioning:** Production AI coworker for autonomous execution across chat, browser, and tools.

## Product Model

Aegis is an always-on assistant that can run tasks autonomously in the background while keeping the user anchored in chat:

1. **Chat panel is the sole operation center**
   - task initiation
   - task status
   - approvals / clarifications
   - final summary and outcomes
2. **Browser panel is an execution tool surface**
   - browser actions and live page state stay in the browser section while running
   - browser actions are summarized back to chat on completion (or critical failure)
3. **No silent failures**
   - every start request must produce an explicit ack or explicit error
   - every task must end with a terminal state (completed / failed / cancelled)

---

## Absolute Rules

### 1) Never hardcode secrets
- No API keys, tokens, passwords, or credentials in code.
- Secrets must be loaded from `.env` through centralized config modules.
- `.env.example` contains placeholders only.

### 2) Update ONBOARDING.md after every pass
At the end of every coding session append:
- what changed
- what works / what does not
- next steps
- blockers / decisions

### 3) Engineering quality baseline
- Type hints on Python function signatures
- Docstrings on public functions/classes
- Structured logging (no `print()` debugging)
- Meaningful error handling (no bare `except:`)
- Focused commits with clear messages

---

## Reliability Contract

### Protocol expectations
- Client task start messages include a `request_id`.
- Server returns a fast explicit ack (`accepted/rejected`) with correlation IDs.
- Server emits deterministic task states and exactly one terminal event.

### Runtime guardrails
- Timeouts on model execution
- Max tool-call bound per task
- Cancellation propagation
- Idempotency for duplicated start requests where applicable

### Failure taxonomy
Prefer machine-readable error codes (example set):
- `E_BAD_PAYLOAD`
- `E_START_REJECTED_BUSY`
- `E_START_TIMEOUT`
- `E_MODEL_TIMEOUT`
- `E_TOOL_LIMIT`
- `E_SOCKET_SEND_FAILED`

---

## Architecture Notes

### Frontend (`frontend/`)
- Chat is the only user-facing surface (Phase 5 removed the browser viewport + screenshot stream).
- Screenshots surface only when the agent explicitly invokes the `screenshot` tool — never auto-frames.
- Do not hide start/reject events.

### Backend (`main.py` + `backend/`)
- `main.py` is the FastAPI entrypoint: websocket + REST, session state, bot command routing.
- `backend/runtime/` owns the always-on agent loop:
  - `supervisor.py` — one persistent `Supervisor` per `owner_uid`; durable event queue.
  - `session.py` — per-session context (channel, settings, memory mode, history).
  - `events.py` — `AgentEvent` / `EventKind` taxonomy (CHAT_MESSAGE, TASK_EVENT, etc.).
  - `agent_loop.py` — OpenAI Agents SDK integration + LiteLLM provider routing.
  - `fanout.py` — fan-out registry wiring channel subscribers (websocket, Slack, Telegram, Discord) to the supervisor stream.
  - `persistence.py` — SQLAlchemy models + helpers for `runtime_runs`, `runtime_run_events`, and (Phase 7) `runtime_inbox_events` / `runtime_tool_calls` durability tables.
  - `rehydration.py` — Phase 7 boot-rehydration pass: re-enqueues `pending` inbox rows, terminates `dispatched` rows as `interrupted` with a `run_interrupted` fan-out frame.
  - `integration.py` — FastAPI glue; `runtime_supervisor_enabled()` + startup/shutdown hooks; wires the persistence factory and runs `rehydrate_pending_events` at boot.
  - `tools/native.py` — 40+ native agent tools (non-browser).
  - `mcp_host.py` — real MCP host; Playwright + Browser MCP servers + connector adapters.
- `backend/integrations/` — Slack/Telegram/Discord channel adapters + connector glue.

### Runtime contract
- Exactly one execution path: events are enqueued on the supervisor; the agent loop produces deltas; fan-out delivers them to subscribers.
- Legacy helpers (`_run_navigation_task*`, `_send_initial_frame`, `_on_frame_*`, manual `human_browser_action`) were deleted in Phase 6 — do not re-introduce them.
- Browser is a tool only. It starts lazily via MCP when an agent calls a browser-namespaced tool, and it shuts down with the supervisor.
- **Durability (Phase 7):** every `AgentEvent` accepted by `SessionSupervisor.enqueue` is persisted to `runtime_inbox_events` *before* the worker touches it. On boot, `rehydrate_pending_events` re-queues `pending` rows and terminates `dispatched` rows as `interrupted`. Tool calls are checkpointed to `runtime_tool_calls`. **Never** bypass `enqueue`; the DB ledger is the source of truth for crash recovery.

---

## Delivery Checklist (minimum)

```bash
npm run -w frontend build
python -m py_compile main.py
pytest -q tests/test_runtime_supervisor_smoke.py -q
```
