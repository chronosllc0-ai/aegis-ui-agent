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
  - `persistence.py` — SQLAlchemy models + helpers for `runtime_runs`, `runtime_run_events`, (Phase 7) `runtime_inbox_events` / `runtime_tool_calls` durability tables, and the atomic `finalize_run_and_inbox` helper.
  - `rehydration.py` — Phase 7 boot-rehydration pass: re-enqueues `pending` inbox rows, terminates `dispatched` rows as `interrupted` with a `run_interrupted` fan-out frame, and reconciles `dispatched` inbox rows whose run already finished to the matching terminal status without a spurious frame.
  - `integration.py` — FastAPI glue; `runtime_supervisor_enabled()` + startup/shutdown hooks; wires the persistence factory and runs `rehydrate_pending_events` in a background `_rehydrate_with_retry` task that probes the session factory until ready (`RUNTIME_REHYDRATION_ATTEMPTS`, `RUNTIME_REHYDRATION_INTERVAL_SEC`).
  - `context_window.py` — Phase 8 deterministic prompt-bucket estimator + `RuntimeContextCheckpoint` persistence model. Drives the context meter and the compaction-checkpoint path.
  - `router.py` — Phase 8 FastAPI router exposing `GET /api/runtime/context-meter/{session_id}` (cookie-authenticated, cross-tenant-safe). Mounted on `app` in `main.py`.
  - `tools/native.py` — 40+ native agent tools (non-browser).
  - `mcp_host.py` — real MCP host; Playwright + Browser MCP servers + connector adapters.
- `backend/integrations/` — Slack/Telegram/Discord channel adapters + connector glue.

### Runtime contract
- Exactly one execution path: events are enqueued on the supervisor; the agent loop produces deltas; fan-out delivers them to subscribers.
- Legacy helpers (`_run_navigation_task*`, `_send_initial_frame`, `_on_frame_*`, manual `human_browser_action`) were deleted in Phase 6 — do not re-introduce them.
- Browser is a tool only. It starts lazily via MCP when an agent calls a browser-namespaced tool, and it shuts down with the supervisor.
- **Durability (Phase 7):** every `AgentEvent` accepted by `SessionSupervisor.enqueue` is persisted to `runtime_inbox_events` *before* the worker touches it. On boot, `rehydrate_pending_events` re-queues `pending` rows and terminates `dispatched` rows as `interrupted`. Tool calls are checkpointed to `runtime_tool_calls`. The dispatch hook flips `runtime_runs` and `runtime_inbox_events` to their terminal state in a single commit via `finalize_run_and_inbox`. **Never** bypass `enqueue`; the DB ledger is the source of truth for crash recovery.
- **Context meter + compaction (Phase 8):** the dispatch hook calls `build_prepared_context` before every `Runner.run` and emits a `context_meter` runtime event with eight buckets (`system_prompt`, `active_tools`, `checkpoints`, `workspace_files`, `pinned_memories`, `pending_tool_outputs`, `chat_history`, `current_user_message`). When `projected_pct ≥ COMPACT_THRESHOLD_PCT` (default 90, clamped 50..99), `maybe_create_checkpoint` persists a `runtime_context_checkpoints` row, emits a `compaction_checkpoint` runtime event, and rewrites the next prompt to use the checkpoint summary plus the current user message. Window size is `RUNTIME_CONTEXT_WINDOW_TOKENS` (default 128_000). The UI consumes this via `GET /api/runtime/context-meter/{session_id}`.

---

## Delivery Checklist (minimum)

```bash
npm run -w frontend build
python -m py_compile main.py
pytest -q tests/test_runtime_supervisor_smoke.py -q
```
