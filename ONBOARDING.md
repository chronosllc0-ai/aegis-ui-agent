# ONBOARDING.md — Session Progress Log

> Update this file at the END of every coding session. This is how continuity is maintained between agents and sessions. Newest entries go at the top.

---

## Session 3.2 — March 10, 2026 (Code Review Fixes: Settings Application + Workflow Edit + WS Cleanup)

**Agent:** GPT-5.2-Codex  
**Duration:** ~1 pass

### What Was Done
- Addressed code review P1: session settings are now applied in `orchestrator.execute_task(...)` before runner execution.
  - Added `_apply_session_settings(...)` to consume model/system instruction settings.
  - Added `_build_agent(...)` helper and rebuild logic when session model/personality prompt changes.
- Addressed websocket reconnect lifecycle review item:
  - Hardened reconnect timer handling in `useWebSocket` by clearing existing reconnect timers before scheduling new ones.
  - Disabled `onclose` callback during hook cleanup to prevent reconnect scheduling while disposing.
- Addressed workflows edit review item:
  - `WorkflowsTab` Edit now persists edited instruction to workflow template data via `onChange(...)` instead of running it.
- Addressed workflow save instruction derivation review item:
  - `saveWorkflow` now prefers the selected task history instruction and falls back to first user-navigation step for the active task.
  - Added guard filters to avoid system/config/queue messages being used as saved workflow instructions.

### What's Working
- Backend tests pass (`pytest -q`).
- Frontend production build passes (`cd frontend && npm run build`).
- Session settings are now functionally consumed before task execution.
- Workflow edit behavior now updates templates correctly without accidental execution.

### What's NOT Working Yet
- Browser screenshot capture for this pass failed due a browser-container Chromium crash (SIGSEGV) in this environment.

### Next Steps
1. Extend settings application to include behavior flags in orchestrator/tool invocation semantics.
2. Add targeted tests for `_apply_session_settings(...)` behavior and workflow-edit persistence.
3. Re-run screenshot capture in a stable browser environment.

### Blockers
- Browser container Playwright/Chromium instability (SIGSEGV) during screenshot attempt.

---

## Session 3.1 — March 10, 2026 (Pass 3.1: Regression Recovery + Product Shell Merge)

**Agent:** GPT-5.2-Codex  
**Duration:** ~1 pass

### Regressions Found
- Pass 3A regressed the previously polished dashboard experience: onboarding empty state was flattened, top bar polish and browser-style URL strip were reduced, ActionLog hierarchy/detail was simplified, and input/steering UX lost keyboard/polish parity.
- Workflow fallback view was functional but visually weak for demos.

### What Was Restored / Improved
- Restored premium dashboard shell while keeping the new product architecture:
  - Rich onboarding empty state in `ScreenView` (logo, headline, subtext, 4 clickable examples, helper text).
  - Polished top bar (Aegis branding, status pill, session timer, New Session).
  - Browser copilot URL/navigation strip (back/forward, current URL, Go submit).
  - Enhanced ActionLog hierarchy (grouped by task, icons, status color coding, timestamp + elapsed seconds, copy log).
  - Restored polished input + steering UX (segmented mode control, queue badge, multiline input, keyboard shortcuts, send spinner, queue panel).
- Preserved all Pass 3 product additions:
  - Sidebar history/search and bottom user area.
  - Settings full-page tabs and return flow.
  - Workflow toggle + save workflow.
  - Settings context persistence and websocket `config` sends.
  - Backend `workflow_step` and MCP integration scaffolding.
- Improved workflow fallback visualization to be intentionally demo-ready:
  - Ordered execution flow with parent relationships,
  - Clear status styling,
  - Right-hand step detail inspector.
- Added lightweight dev/demo seed data to validate all major surfaces without live backend dependence:
  - 3+ history items,
  - 2+ workflow templates,
  - 4+ action log entries,
  - Multi-step workflow graph data,
  - Integrations in mixed states,
  - Auth view/sign-out state for auth screenshot.

### Screenshot Evidence Captured
- Captured screenshot set (artifact paths) and manifest at `docs/screenshots/README.md`.
- Captured names:
  - `01-dashboard-onboarding.png`
  - `02-dashboard-sidebar-history.png`
  - `03-dashboard-active-log.png`
  - `04-settings-profile.png`
  - `05-settings-agent-config.png`
  - `06-settings-integrations.png`
  - `07-settings-workflows.png`
  - `08-workflow-view.png`
  - `09-auth-page.png`
- Artifact location prefix:
  - `browser:/tmp/codex_browser_invocations/388ce2e154a537fe/artifacts/docs/screenshots/`

### What's Working
- Frontend build passes with restored non-regressed shell and settings/workflow integration.
- Backend tests remain green.
- Dashboard + settings + workflow + auth surfaces are all visually verified.

### What's Stubbed / Incomplete
- React Flow dependency remains unavailable in this environment; enhanced fallback workflow view is used.
- Firestore sync is still placeholder-only.
- MCP/messaging connectors remain mocked wiring (not live external APIs).

### What Still Feels Weak
- History replay is currently log-focused and not full screenshot timeline playback yet.
- Sidebar responsive behavior is solid but could benefit from animation polish and persistent collapsed state.

### Next Steps
1. Add real task replay timeline with screenshot snapshots per step.
2. Replace workflow fallback with React Flow when package install becomes available.
3. Implement Firestore sync and real messaging connector APIs with secure token handling.

### Blockers
- npm registry restrictions still prevent installing `reactflow` in this environment.

---

## Session 3 — March 9, 2026 (Pass 3A: Settings + Integrations + Workflow Wiring)

**Agent:** GPT-5.2-Codex  
**Duration:** ~1 pass

### What Was Done
- Rebuilt the frontend shell around a persistent sidebar with top/middle/bottom sections: `New Task`, history search, workflow/settings shortcuts, and user avatar menu.
- Added a full-page Settings experience with left tab nav and right content pane. New tabs implemented: `Profile`, `Agent Configuration`, `Integrations`, and `Workflows`.
- Added app-wide settings state (`SettingsContext` + `useSettings`) with localStorage persistence, theme toggle state, workflow template storage, and websocket session config payload generation.
- Added `UserMenu` dropdown entry point to Settings and a second entry point from sidebar settings gear/shortcut.
- Added workflow visualization toggle in Action Log and implemented a fallback workflow view component that renders step cards from structured workflow websocket events.
- Added “Save as Workflow” behavior from ActionLog and run/edit/delete controls in Workflows settings tab.
- Added client MCP helpers/types and integrations UI supporting built-in integrations plus custom MCP server form (`authType`, URL, test/save stubs).
- Added backend MCP + messaging stubs:
  - `mcp_client.py` user-scoped registry and tool forwarding scaffold
  - `integrations/base.py` interface
  - `integrations/telegram.py`, `integrations/slack_connector.py`, `integrations/discord.py` mocked connectors and tool manifests
  - `integrations/__init__.py` exports
- Extended websocket backend contract with:
  - `config` action to receive per-session settings
  - `workflow_step` event emission for graph/list rendering payloads
  - pass-through of settings/workflow callbacks into orchestrator execution
- Extended orchestrator to emit structured workflow steps (id/parent/action/description/status/timestamp/duration/screenshot).

### What's Working
- `pytest` suite remains green (3 tests).
- Frontend builds successfully with the new settings/integrations/workflow UI wiring.
- Settings persist in localStorage and are sent as websocket `config` before task starts.
- Backend emits `workflow_step` payloads while task steps stream.

### What's NOT Working Yet
- Real reactflow graph was requested, but npm registry access is blocked in this environment (403), so a fallback card-based workflow view is used.
- Firestore sync is currently a no-op stub in `useSettings`; local persistence is working.
- MCP protocol networking and messaging APIs are intentionally stubbed/mocked (tool manifests + execute paths wired, not full external API calls).
- Token encryption-at-rest is not implemented yet; UI only stores masked display values.

### Next Steps
1. Replace fallback workflow cards with real React Flow + auto-layout (dagre/elk) once package install is available.
2. Implement authenticated Firestore settings/workflow sync (read/write + conflict strategy).
3. Wire MCP client to real HTTP MCP servers with retries, auth handling, and per-user persisted server configs.
4. Implement real Telegram/Slack/Discord API clients with secure token storage and live status polling.
5. Add tests for settings serialization, workflow persistence, and websocket `workflow_step` schema contract.

### Decisions Made
- Prioritized end-to-end UI/data-flow wiring with stubs over full external API integration per pass instructions.
- Chose fallback workflow rendering due to blocked dependency install to keep build green.

### Blockers
- npm package fetch for `reactflow` blocked by registry 403 in this environment.

---

## Session 2.6 — March 9, 2026 (Review Fixes: Socket Stability + Interrupt Safety)

**Agent:** GPT-5.2-Codex  
**Duration:** ~1 pass

### What Was Done
- Addressed Codex review feedback in `frontend/src/hooks/useWebSocket.ts` by decoupling socket lifecycle from task-id changes.
- Removed unintended websocket reconnect churn caused by `activeTaskId` dependency capture:
  - Introduced `activeTaskIdRef` for message handlers,
  - Kept `connect` stable (depends only on stable logger callback),
  - Added `shouldReconnectRef` to avoid reconnect scheduling on intentional cleanup/unmount.
- Addressed backend interrupt race in `main.py`:
  - Interrupt now sets cancellation and waits for the currently running task to settle before starting the new task,
  - Prevents `cancel_event` from being cleared by a new task before prior task has observed cancellation.
- Addressed stuck `task_running` failure path in `main.py`:
  - Wrapped navigation execution in `try/except/finally`,
  - Ensures `task_running` is always reset even on runtime failures,
  - Emits websocket error/result payloads when task execution fails.
- Added `_start_navigation_task(...)` helper to centralize task creation and reduce duplicated task-launch code paths.

### What's Working
- Backend tests pass after race/failure handling changes.
- Frontend production build passes after websocket-hook stabilization changes.
- WebSocket connection remains stable when starting new tasks (no reconnect churn triggered by task id state updates).

### What's NOT Working Yet
- Queue deletion is still UI-local and not yet synchronized with backend queue removal/reorder protocol.
- Action metadata is still partially inferred client-side from freeform step text.

### Next Steps
1. Add server-side queue IDs and delete/reorder websocket actions for full queue sync.
2. Emit structured step payload fields from backend (e.g., `action_kind`, `target`, `url`) to reduce frontend heuristics.
3. Add targeted tests for interrupt timing behavior and failure-path task-state reset.

### Decisions Made
- Preserved existing websocket action contract while fixing race conditions internally.
- Kept reconnect behavior automatic but guarded with explicit cleanup semantics.

### Blockers
- None.

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
