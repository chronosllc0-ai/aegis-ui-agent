# ONBOARDING.md — Session Progress Log

> Update this file at the END of every coding session. This is how continuity is maintained between agents and sessions. Newest entries go at the top.

---

## Session 2.5 — March 9, 2026 (UI Polish + UX Upgrades)

**Agent:** GPT-5.2-Codex  
**Duration:** ~1 pass

### What Was Done
- Polished the frontend UX while preserving the core layout and websocket protocol.
- Added a richer header with Aegis branding, semantic connection status labels/dots, live session timer, and a `New Session` reset button.
- Added a URL command bar between header and screen panel, including back/forward controls, URL display/edit input, and direct navigation submit behavior.
- Replaced the blank screen empty state with an onboarding hero: large Aegis icon, “Tell me what to do”, and 4 clickable example prompt cards that submit instantly.
- Upgraded `ScreenView` with a thin top progress indicator while working and crossfade transitions between incoming screenshot frames.
- Enhanced input UX: multiline textarea, keyboard hints, `Enter` send, `Shift+Enter` newline, `Esc` clear, `Tab` mode cycle, steer glow, interrupt warning border, queue badge, and send loading spinner.
- Enhanced log UX: grouped entries by task (collapsible), per-step icons, status color coding, elapsed time per step, smooth autoscroll, and Copy Log export button.
- Added responsive behavior: narrow-screen log collapse/restore affordance and draggable divider for desktop panel resizing.
- Added success/error toast feedback and dynamic tab title (`Aegis` vs `Aegis · Working...`).
- Added shield favicon (`frontend/public/shield.svg`) and updated `index.html` title/favicon metadata.

### What's Working
- Frontend builds cleanly with all polish features enabled.
- Empty-state example prompts can trigger task submission flow immediately.
- Action log grouping, collapse, color coding, and copy export work in-browser.
- Dynamic title, toasts, and frame transitions are functioning.
- URL bar and header controls are wired to websocket command flow without protocol changes.

### What's NOT Working Yet
- Back/forward controls currently send steering text commands (`go back`, `go forward`) rather than explicit dedicated backend actions.
- Queue item removal remains client-side UI only (no backend dequeue protocol yet).
- Voice-active mic animation is wired as a UI placeholder only pending Pass 3 live audio integration.

### Next Steps
1. Pass 3 voice integration: connect mic state + audio stream to websocket `audio_chunk` flow and playback handling.
2. Add server-side queue item IDs and delete/reorder protocol for fully synchronized queue UX.
3. Enrich websocket step payloads with structured action metadata (`action_kind`, `url`, `timings`) to reduce frontend heuristics.
4. Add focused frontend tests for log grouping, keyboard shortcuts, and mode styling states.

### Decisions Made
- Preserved existing websocket envelope/actions as requested; all polish is layered in UI/hook behavior.
- Kept dark product aesthetic and Tailwind-only styling.

### Blockers
- None blocking Pass 2.5 completion.

---

## Session 2 — March 9, 2026 (Pass 2 Frontend + Real-time Steering)

**Agent:** GPT-5.2-Codex  
**Duration:** ~1 pass

### What Was Done
- Scaffolded a new React + TypeScript Vite app in `frontend/`, installed dependencies, and added Tailwind via `@tailwindcss/vite`.
- Built the pass-2 UI shell with a dark dashboard layout in `App.tsx`: `ScreenView` (left), `ActionLog` (right), and `InputBar`/steering controls at the bottom.
- Implemented frontend components:
  - `ScreenView` for live frame rendering, pulsing working border, and transient “Steering...” overlay.
  - `ActionLog` with timestamped step feed, monospace styling, and interrupt emphasis.
  - `InputBar` that is always interactive, includes mode-aware send behavior + mic button UI.
  - `SteeringControl` segmented toggle (`Steer` default, `Interrupt`, `Queue`).
  - `MessageQueue` collapsible queued instruction list with count badge and per-item delete.
- Added `useWebSocket` hook with connect/disconnect/reconnect handling, routing of `step`/`result`/`frame`/`error` messages, and connection status state.
- Added Vite dev proxy for `/ws/*` to `http://localhost:8080` with WebSocket forwarding.
- Updated backend `main.py` for pass-2 steering protocol support:
  - Per-session runtime state (`task_running`, `cancel_event`, steering context list, queue).
  - New actions: `steer`, `interrupt`, `queue`, plus existing `navigate`/`stop`/`audio_chunk`.
  - Background task execution so users can send steering while task is running.
  - Queue draining after active task completes.
  - Frame streaming over websocket as `{"type":"frame","data":{"image":...}}`.
- Updated `orchestrator.py` to support frame callbacks, cancellation checks, and steering-context checks between streamed steps.
- Updated Dockerfile to multi-stage build frontend (`frontend/dist`) and run FastAPI with uvicorn.
- Updated FastAPI to serve `frontend/dist` (assets + SPA fallback route) in production.
- Updated websocket smoke test to validate frame + step + result flow.

### What's Working
- Frontend builds successfully (`npm run build`) and outputs to `frontend/dist`.
- Backend test suite passes (`pytest tests/ -v`).
- WebSocket smoke test validates frame, step, and result event flow.
- Steering UI allows continuous input regardless of agent run-state.
- Interrupt and queue actions are accepted and logged in real time.

### What's NOT Working Yet
- Live backend semantics for “steer changes next tool decision” are still a first-pass implementation; steering context is checked between streamed events but not yet deeply fused into ADK reasoning.
- Queue deletion is currently frontend-only; if an item was already sent with `queue`, removing it in UI does not yet retract it server-side.
- Vite dev server logs proxy warnings when backend is not running (expected in isolated frontend dev).

### Next Steps
1. Add explicit orchestrator/tool-level consumption of steering messages before each tool call for tighter behavior.
2. Add backend protocol support to remove/reorder queued items from UI (queue IDs + delete action).
3. Stream richer result payloads to UI (task summaries, completion metadata, errors).
4. Start Pass 3 voice path: wire mic capture to `audio_chunk` websocket messages and playback for responses.
5. Add integration tests for interrupt + queue lifecycle.

### Decisions Made
- Frontend↔backend communication remains websocket-only, including queue/interrupt/steer controls.
- Default mode remains `Steer`, while first submission in idle state maps to `navigate`.
- Production frontend hosting is handled by FastAPI static + SPA fallback, avoiding separate Nginx layer.

### Blockers
- None blocking pass completion.

---

## Session 1 — March 8, 2026 (Phase 1 Core Loop Hardening)

**Agent:** GPT-5.2-Codex
**Duration:** ~1 pass

### What Was Done
- Installed Python dependencies from `requirements.txt` (already satisfied in this environment).
- Attempted `playwright install chromium`; blocked by CDN 403 (`Domain forbidden`) in this environment.
- Created local `.env` from `.env.example` (placeholder values retained; no key was available in env).
- Refactored runtime imports to match the actual flat repo layout (removed broken `src.*` imports).
- Reworked core modules (`executor.py`, `analyzer.py`, `navigator.py`, `orchestrator.py`, `main.py`, `session.py`, `config.py`) with stricter type hints, async-safe Gemini calls, structured parsing, and model detection utility.
- Added `aegis_logging.py` and removed the logging module naming conflict by moving setup there.
- Added Phase-1 validation tests: executor PNG bytes test, analyzer response parsing test, and websocket endpoint smoke test with stub orchestrator.
- Added `scripts/ws_smoke_client.py` for manual websocket flow testing against a running local server.

### What's Working
- `pytest` suite added in this pass is green (`3 passed`).
- Core modules compile and import successfully with installed ADK path (`google.adk.agents` / `google.adk.runners`).
- FastAPI websocket endpoint path and request/response envelope are validated by test client.
- Analyzer now requests strict JSON and normalizes parsed UI element output.

### What's NOT Working Yet
- Real browser runtime is blocked until Chromium download succeeds (`playwright install chromium` currently fails with 403 in this environment).
- Real Gemini calls cannot be validated without a real `GEMINI_API_KEY` in `.env`.
- End-to-end instruction execution (`go to google.com and search weather`) remains blocked by the two constraints above (browser binary + API key).

### Next Steps
1. Provide a real `GEMINI_API_KEY` in `.env` (local/CI secret injection).
2. Resolve Playwright browser install path (mirror, allowed domain, or pre-baked browser in runtime image).
3. Run true E2E check: orchestrator task `go to google.com and search for weather in new york`.
4. Run `uvicorn main:app` + `scripts/ws_smoke_client.py` against real Gemini + browser and capture logs/artifacts.
5. Expand tests to include mocked orchestrator event stream and analyzer contract validation fixtures.

### Decisions Made
- Defaulted configurable model to `gemini-2.5-pro` with dynamic availability probing for `gemini-3-pro` / preview variants when API key is present.
- Updated ADK imports to current installed package paths (`google.adk.agents.Agent`, `google.adk.runners.Runner`).

### Blockers
- No real Gemini API key available in this environment.
- Playwright Chromium CDN blocked (403 Domain forbidden).

---

## Session 0 — March 8, 2026 (Project Bootstrap)

**Agent:** Viktor (via Slack)
**Duration:** Initial scaffold

### What Was Done
- Created full project scaffold with all source files
- Wrote `AGENTS.md` (the master guide you're reading alongside this)
- Set up project structure: `src/agent/`, `src/live/`, `src/utils/`, `frontend/`, `tests/`, `scripts/`
- Wrote core modules:
  - `src/main.py` — FastAPI + WebSocket server
  - `src/agent/orchestrator.py` — ADK agent with tool registration
  - `src/agent/analyzer.py` — Gemini vision screenshot analysis
  - `src/agent/executor.py` — Playwright browser control
  - `src/agent/navigator.py` — ADK-compatible tool functions
  - `src/live/session.py` — Live API session scaffolding
  - `src/utils/config.py` — Pydantic Settings
  - `src/utils/logging.py` — Structured logging
- Created deployment files: `Dockerfile`, `cloudbuild.yaml`, `scripts/deploy.sh`
- Created `requirements.txt`, `.env.example`, `.gitignore`
- Wrote full `README.md` with architecture diagram

### What's Working
- Project structure is complete and follows best practices
- All modules have proper type hints, docstrings, and async patterns
- Dockerfile and deploy scripts are ready
- No secrets in codebase (verified)

### What's NOT Working Yet
- No code has been tested (no API key set up yet)
- Frontend not yet created (React app needs scaffolding)
- Live API voice integration is stubbed, not implemented
- Tests directory is empty
- No GCP project configured

### Next Steps (Priority Order)
1. **Install dependencies and verify imports** — `pip install -r requirements.txt && playwright install chromium`
2. **Get a Gemini API key** and add to `.env`
3. **Test the core loop locally:**
   - Start with `executor.py`: can it launch a browser and take screenshots?
   - Then `analyzer.py`: does Gemini return useful UI analysis?
   - Then `navigator.py` + `orchestrator.py`: can the agent complete a simple task like "go to google.com and search for weather"?
4. **Build the React frontend** — voice controls, screen view, action log
5. **Implement Live API voice** — replace the stub in `session.py`
6. **Deploy to Cloud Run** — test with `scripts/deploy.sh`
7. **Record demo video** (< 4 min) before March 16

### Decisions Needed
- Which Gemini model version to use (verify `gemini-3-pro` availability vs `gemini-2.5-pro`)
- Whether to use Computer Use tool directly or custom screenshot+click approach
- Firestore schema for session state

### Blockers
- None currently. Just need API key and GCP project.

---

<!-- 
TEMPLATE FOR NEW ENTRIES (copy this for each session):

## Session N — [Date]

**Agent:** [Name]
**Duration:** [Approximate time spent]

### What Was Done
- 

### What's Working
- 

### What's NOT Working Yet
- 

### Next Steps
1. 

### Decisions Made
- 

### Blockers
- 
-->
