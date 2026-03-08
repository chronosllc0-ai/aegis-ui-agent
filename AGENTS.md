# AGENTS.md — Aegis UI Navigator

> This file is the single source of truth for any AI coding agent (Codex, Kilocode, Cursor, etc.) working on this project. Read this FIRST on every session. Update ONBOARDING.md after every pass.

## Project Identity

**Name:** Aegis
**Tagline:** AI-powered universal UI navigator
**Competition:** Gemini Live Agent Challenge 2026 (Devpost)
**Track:** UI Navigator (visual UI understanding & interaction)
**Deadline:** March 16, 2026 @ 5:00 PM PDT
**Repo:** `chronosllc0-ai/aegis-ui-agent`

## What Aegis Does

Aegis is an agent that can operate ANY website or app by "seeing" the screen. Users give natural language instructions (text or voice), and Aegis:

1. Takes a screenshot of the current browser state
2. Sends the screenshot to Gemini's multimodal vision to understand the UI layout
3. Identifies interactive elements (buttons, inputs, links, menus) without DOM access
4. Executes the right action (click, type, scroll) via Playwright
5. Captures a new screenshot and repeats until the task is complete
6. Narrates progress back to the user via voice (Gemini Live API)

No DOM parsing. No CSS selectors. No APIs. Pure visual intelligence.

---

## ABSOLUTE RULES

### 1. NO SECRETS IN CODE — EVER
- **Never** hardcode API keys, tokens, passwords, or credentials anywhere in the codebase
- All secrets go in `.env` (which is gitignored) and are accessed via `src/utils/config.py`
- Use `.env.example` to document required variables with placeholder values only
- If you need a new secret, add it to `Settings` in `config.py` and to `.env.example`
- Before every commit, mentally scan for leaked secrets. If in doubt, don't commit.

### 2. UPDATE ONBOARDING.md AFTER EVERY PASS
- At the end of every coding session, update `ONBOARDING.md` with:
  - What you built or changed
  - What's working and what's not
  - What should be done next
  - Any blockers or decisions needed
- This is how continuity is maintained between sessions. Treat it as sacred.

### 3. BEST PRACTICES
- Type hints on all function signatures
- Docstrings on all public functions and classes
- Async/await throughout (no blocking calls)
- Error handling with meaningful messages (no bare `except:`)
- Structured logging via `src/utils/logging.py` (no `print()` statements)
- Small, focused commits with clear messages
- No `# TODO` without a clear description of what needs doing

---

## Competition Requirements (Must-Haves)

All of these are REQUIRED for a valid submission:

| Requirement | How We Meet It |
|---|---|
| Use a Gemini model via Google GenAI SDK or ADK | Gemini 3 Pro for vision analysis + ADK for orchestration |
| At least one Google Cloud service | Cloud Run (hosting) + Firestore (session state) + Cloud Storage (screenshots) |
| Hosted on Google Cloud | Deployed to Cloud Run via `scripts/deploy.sh` |
| Project must be new (built for this hackathon) | Started March 2026 |
| Public code repo with README | This repo |
| Demo video (< 4 minutes) | To be recorded before submission |
| Architecture diagram | In README.md |
| Text description on Devpost | To be written before submission |
| Proof of GCP deployment | Cloud Run URL in submission |

### Judging Criteria
- **Innovation & Multimodal UX (40%)** — How creative and useful is the multimodal interaction?
- **Technical Implementation (30%)** — Quality of code, architecture, and use of Gemini/GCP
- **Remaining 30%** — Impact, polish, and presentation

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Frontend (React)               │
│  Voice Input ←→ Live API ←→ Screen Capture       │
└──────────────────────┬──────────────────────────┘
                       │ WebSocket
┌──────────────────────▼──────────────────────────┐
│              Backend (FastAPI on Cloud Run)       │
│                                                   │
│  ┌─────────────┐  ┌────────────┐  ┌───────────┐ │
│  │ ADK Agent   │  │ Screenshot │  │ Action    │ │
│  │ Orchestrator│←→│ Analyzer   │←→│ Executor  │ │
│  └─────────────┘  └────────────┘  └───────────┘ │
│         │                              │         │
│  ┌──────▼──────┐              ┌───────▼───────┐ │
│  │ Gemini 3    │              │  Playwright   │ │
│  │ Live API    │              │  Browser      │ │
│  └─────────────┘              └───────────────┘ │
└──────────────────────┬──────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │    Google Cloud Platform     │
        │  Cloud Run · Firestore ·     │
        │  Cloud Storage · Logging     │
        └─────────────────────────────┘
```

## Tech Stack

| Component | Technology | Why |
|---|---|---|
| AI Model | Gemini 3 Pro | Multimodal vision + Computer Use capability |
| Agent Framework | Google ADK | Required by competition, handles tool orchestration |
| Real-time Voice | Gemini Live API | Bidirectional audio streaming for voice control |
| Browser Automation | Playwright | Headless Chromium, async-native, screenshot capture |
| Backend | Python 3.11 / FastAPI | Async, WebSocket support, fast |
| Frontend | React + Vite + TypeScript | Modern, fast builds, good DX |
| Hosting | Google Cloud Run | Serverless containers, auto-scaling |
| Session State | Firestore | Real-time, serverless, GCP-native |
| Screenshot Storage | Cloud Storage | Blob storage for audit trail |
| CI/CD | Cloud Build | GCP-native, auto-deploy on push |

---

## Project Structure

```
aegis-ui-agent/
├── AGENTS.md                # YOU ARE HERE — read this first
├── ONBOARDING.md            # Session-by-session progress log
├── README.md                # Public-facing docs + architecture
├── src/
│   ├── main.py              # FastAPI app + WebSocket endpoints
│   ├── agent/
│   │   ├── orchestrator.py  # ADK agent setup, tool registration
│   │   ├── navigator.py     # Tool functions (click, type, scroll, screenshot)
│   │   ├── analyzer.py      # Screenshot → UI understanding via Gemini vision
│   │   └── executor.py      # Playwright browser control (action primitives)
│   ├── live/
│   │   └── session.py       # Gemini Live API session management
│   ├── tools/               # Additional tool modules as needed
│   └── utils/
│       ├── config.py        # Pydantic Settings (reads .env)
│       └── logging.py       # Structured logging setup
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── VoiceControl.tsx    # Mic input + Live API voice
│   │   │   ├── ScreenView.tsx      # Live browser view
│   │   │   └── ActionLog.tsx       # Step-by-step action feed
│   │   └── hooks/
│   │       └── useLiveAPI.ts       # WebSocket hook for Live API
│   ├── package.json
│   └── vite.config.ts
├── tests/
│   ├── test_analyzer.py
│   ├── test_executor.py
│   └── test_navigator.py
├── scripts/
│   ├── deploy.sh            # One-command Cloud Run deploy
│   └── setup_gcp.sh         # GCP project bootstrapping
├── Dockerfile
├── cloudbuild.yaml
├── requirements.txt
├── .env.example             # Template (NO real secrets)
└── .gitignore
```

---

## How Each Module Works

### `src/main.py`
FastAPI app with two main endpoints:
- `GET /health` — health check for Cloud Run
- `WS /ws/navigate` — WebSocket for real-time navigation sessions

The WebSocket accepts JSON messages:
- `{"action": "navigate", "instruction": "..."}` — execute a task
- `{"action": "audio_chunk", "audio": "..."}` — voice input via Live API
- `{"action": "stop"}` — end session

### `src/agent/orchestrator.py`
Sets up the ADK Agent with all navigation tools registered. The agent receives a natural language instruction, breaks it into steps, and calls tools in sequence. Uses `InMemorySessionService` for state (swap to Firestore for production).

### `src/agent/analyzer.py`
Takes a PNG screenshot (bytes), base64-encodes it, sends to Gemini 3 Pro with a structured prompt asking it to identify:
- Page type (search results, form, dashboard, etc.)
- Interactive elements with approximate coordinates
- Current state (errors, loading, popups)
- Navigation context (URL, breadcrumbs)

Returns structured `ScreenAnalysis` with list of `UIElement` objects.

### `src/agent/executor.py`
Playwright wrapper. Launches headless Chromium at 1280x720. Exposes primitives:
- `screenshot()` → PNG bytes
- `goto(url)` → navigate
- `click(x, y)` → mouse click
- `type_text(text, x, y)` → click + type
- `press_key(key)` → keyboard
- `scroll(direction, amount)` → mouse wheel
- `go_back()` → history back

### `src/agent/navigator.py`
Bridges analyzer + executor into ADK-compatible async tool functions. Each function has a clear docstring (ADK uses these for the agent's tool descriptions).

### `src/live/session.py`
Manages Gemini Live API WebSocket sessions. Handles:
- Session creation with system instruction
- Audio chunk forwarding
- Transcription extraction
- Session cleanup

### `src/utils/config.py`
Pydantic `BaseSettings` that reads from `.env`. All secrets and config live here. Never import `os.environ` directly elsewhere.

---

## Build Order (Recommended)

If starting from scratch or picking up where the last session left off, follow this order:

### Phase 1: Core Loop (Get it working locally)
1. `executor.py` — Playwright browser control, verify screenshots work
2. `analyzer.py` — Send screenshots to Gemini, verify UI element detection
3. `navigator.py` — Wire tools together
4. `orchestrator.py` — ADK agent with tools, test with simple tasks
5. `main.py` — FastAPI + WebSocket, test from CLI/Postman

### Phase 2: Voice (Add Live API)
6. `session.py` — Gemini Live API integration for voice input/output
7. Wire voice into the WebSocket flow in `main.py`

### Phase 3: Frontend
8. React app with WebSocket connection
9. `VoiceControl.tsx` — mic capture + playback
10. `ScreenView.tsx` — display browser screenshots in real-time
11. `ActionLog.tsx` — show step-by-step actions

### Phase 4: Cloud Deploy
12. Dockerfile working locally
13. `deploy.sh` — push to Cloud Run
14. Swap InMemorySessionService for Firestore
15. Add Cloud Storage for screenshot audit trail

### Phase 5: Polish for Submission
16. Error recovery (popups, CAPTCHAs, 404s)
17. Multi-tab support
18. Architecture diagram (for Devpost)
19. Demo video (< 4 minutes)
20. Devpost submission text

---

## Key API Patterns

### Gemini Vision (Screenshot Analysis)
```python
from google import genai

client = genai.Client(api_key=settings.GEMINI_API_KEY)
response = client.models.generate_content(
    model="gemini-3-pro",
    contents=[{
        "role": "user",
        "parts": [
            {"text": "Analyze this screenshot..."},
            {"inline_data": {"mime_type": "image/png", "data": base64_screenshot}},
        ],
    }],
)
```

### ADK Agent Setup
```python
from google.adk import Agent, Runner
from google.adk.sessions import InMemorySessionService

agent = Agent(
    name="aegis_navigator",
    model="gemini-3-pro",
    description="UI navigation agent",
    instruction="You navigate UIs by seeing screenshots...",
    tools=[take_screenshot, click_element, type_text, ...],
)

runner = Runner(agent=agent, app_name="aegis", session_service=InMemorySessionService())
async for event in runner.run_async(user_id="user", session_id=sid, new_message=instruction):
    # process events
```

### Gemini Live API (Voice)
```python
from google import genai

client = genai.Client(api_key=settings.GEMINI_API_KEY)
config = {"response_modalities": ["AUDIO", "TEXT"]}

async with client.aio.live.connect(model="gemini-2.5-flash-native-audio-preview", config=config) as session:
    await session.send_realtime_input(audio={"data": audio_bytes, "mime_type": "audio/pcm"})
    async for response in session.receive():
        # handle audio/text responses
```

---

## Environment Variables

All defined in `src/utils/config.py`, loaded from `.env`:

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Google AI API key for Gemini |
| `GOOGLE_CLOUD_PROJECT` | Yes (for deploy) | GCP project ID |
| `PORT` | No (default: 8080) | Server port |
| `LOG_LEVEL` | No (default: INFO) | Logging level |
| `BROWSER_HEADLESS` | No (default: true) | Run browser headless |
| `VIEWPORT_WIDTH` | No (default: 1280) | Browser viewport width |
| `VIEWPORT_HEIGHT` | No (default: 720) | Browser viewport height |

---

## Testing

Run tests with:
```bash
pytest tests/ -v
```

Write tests for:
- `test_executor.py` — Browser launches, screenshots return bytes, click/type work
- `test_analyzer.py` — Mock Gemini response, verify parsing
- `test_navigator.py` — Integration: screenshot → analyze → act

---

## Gotchas & Tips

- Playwright needs `playwright install chromium` after pip install
- Cloud Run has a 300s default timeout; complex navigation tasks may need more
- Gemini vision works best with 1280x720 screenshots (matches common resolution)
- The ADK agent's tool docstrings are critical; Gemini uses them to decide which tool to call
- Live API audio format: input 16-bit PCM 16kHz mono, output 24kHz
- Always `await page.wait_for_timeout(500)` after clicks to let the page settle
- For coordinate accuracy, avoid full-page screenshots; use viewport-only
