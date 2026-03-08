# ONBOARDING.md — Session Progress Log

> Update this file at the END of every coding session. This is how continuity is maintained between agents and sessions. Newest entries go at the top.

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
