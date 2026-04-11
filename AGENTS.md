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

### Frontend
- Chat is command center.
- Browser is a tool viewport.
- Do not hide start/reject events.
- Keep low-level browser noise out of chat during run; provide concise completion summary.

### Backend
- Normalize and validate inbound payloads.
- Preserve original client metadata when logging.
- Emit explicit protocol states.
- Always produce terminal outcomes.

### Runtime
- Provider-agnostic orchestration with safe tool bridging.
- Fallback runtime behavior is explicit and observable.

---

## Delivery Checklist (minimum)

```bash
npm run -w frontend build
python -m py_compile main.py backend/pydantic_adk_runner.py
pytest -q tests/test_main_websocket.py::test_websocket_navigate_smoke -q
```
