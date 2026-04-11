# OpenClaw-Informed Runtime Rebuild Prompt (Repo-Tailored)

## Why this exists
Aegis currently has a silent-failure class where chat-panel sends can appear as local user bubbles but not reliably start observable execution. This prompt rebuilds the send/control-plane loop in one deterministic pass.

## External reference baseline (research)
- OpenClaw positions a **Gateway WebSocket control plane** as the single orchestration surface for sessions, tools, and events: https://raw.githubusercontent.com/openclaw/openclaw/main/README.md
- OpenClaw docs index emphasizes channel routing, model failover, streaming/chunking, and skill install gating. Mirror those principles in Aegis runtime contracts (typed events, deterministic state transitions, and explicit fallback behavior).
- OpenClaw repo: https://github.com/openclaw/openclaw

## Aegis product direction alignment
- Chat panel is the **sole operation center** for user-agent communication.
- Browser panel is a tool viewport only; browser operations remain in Action Log and should not pollute chat.
- Mode selector must reflect active runtime mode transitions (selected vs delegated).

---

## One-go execution prompt

```md
Task: Rebuild Aegis prompt dispatch and runtime event flow to eliminate silent failures and make chat the single control center.

Targets:
- frontend/src/App.tsx
- frontend/src/components/ChatPanel.tsx
- frontend/src/hooks/useWebSocket.ts
- main.py
- ONBOARDING.md

### Phase 1 — Canonical send pipeline
1) Introduce one App-level canonical dispatch function for all prompt sources:
   - chat composer send
   - browser example prompt click
   - quick action triggers
2) Every send gets a `client_request_id` and `send_source` metadata.
3) Remove hardcoded mode/action logic from ChatPanel submit path; ChatPanel must delegate to canonical App dispatcher.

Acceptance:
- Browser example and chat submit hit the same function and payload shape.

### Phase 2 — Action selection hardening (silent-failure guard)
1) In App handleSend, detect stale `isWorking` via terminal-log guard:
   - if latest log is result/error/interrupt, treat runtime as idle.
2) If user submits while runtime looks idle, send `navigate` (never `steer`).
3) Keep queue/interrupt explicit paths unchanged.

Acceptance:
- No `steer`-while-idle no-op behavior.

### Phase 3 — WebSocket control-plane observability
1) Emit/propagate `client_request_id` through websocket and backend logs.
2) Log milestones with request id:
   - websocket received
   - task start
   - provider/model selection
   - model loop start
   - result/error emitted
3) Include `task_id` in step/result/error payloads.

Acceptance:
- A failed run is diagnosable in one request-id trace.

### Phase 4 — Backend recovery consistency
1) Keep `steer` fallback-to-navigate behavior server-side.
2) Ensure fallback response includes visible task lifecycle events with `task_id`.
3) Do not emit duplicate user-facing errors for the same failure.

Acceptance:
- If frontend sends `steer` in idle state, backend still starts task with clear lifecycle events.

### Phase 5 — Chat UX contract enforcement
1) Chat panel must never render browser-only actions/workflow noise.
2) Chat keeps user prompts + assistant summaries + non-browser tool cards only.
3) Keep ask_user_input responses single-send (no duplicate steer call).

Acceptance:
- Browser actions remain in Action Log only, even after thread refresh/hydration.

### Phase 6 — Tests & checks
Add/extend tests for:
1) chat submit idle => navigate start
2) chat submit working => steer
3) browser example + chat input share canonical dispatcher
4) steer fallback starts task and emits task_id
5) ask_user_input reply emits one response event only
6) frontend build and existing backend tests pass

### Required commands
- cd frontend && npm run build
- pytest -q tests/test_mode_commands.py tests/test_modes.py tests/test_parallel_tool_calls.py

### Delivery notes
- Keep changes backward compatible with existing websocket action names.
- Update ONBOARDING.md with root cause, fix details, and validation evidence.
```
