# Aegis — AI-Powered Universal UI Navigator

> Built for the Gemini Live Agent Challenge 2026

Aegis is an intelligent UI navigation agent that observes your screen, understands visual elements without relying on DOM access, and performs actions based on natural language instructions. Think of it as an AI copilot that can operate any website or application by "seeing" the screen.

## Features

- **Visual UI Understanding** — Interprets screenshots using Gemini's multimodal vision to identify buttons, forms, menus, and interactive elements
- **Natural Language Control** — Tell the agent what to do in plain English: "Fill out the contact form with my info" or "Find the cheapest flight to NYC"
- **Cross-Application Workflows** — Chain actions across multiple websites and apps
- **Real-Time Voice Interaction** — Talk to the agent using Gemini Live API while it navigates for you
- **Smart Error Recovery** — Detects failures (404s, popups, CAPTCHAs) and adapts its approach
- **Action Replay & Audit Trail** — Every action is logged with before/after screenshots for transparency

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

| Component | Technology |
|-----------|-----------|
| AI Model | Gemini 3 Pro (multimodal vision + Computer Use) |
| Agent Framework | Google ADK (Agent Development Kit) |
| Real-time Voice | Gemini Live API (bidirectional streaming) |
| Browser Automation | Playwright |
| Backend | Python / FastAPI |
| Frontend | React + Vite |
| Hosting | Google Cloud Run |
| Storage | Firestore (session state) + Cloud Storage (screenshots) |
| CI/CD | Cloud Build |

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- Google Cloud account with billing enabled
- Gemini API key ([Get one here](https://ai.google.dev/))

### Setup

```bash
# Clone the repo
git clone https://github.com/chronosllc0-ai/aegis-ui-agent.git
cd aegis-ui-agent

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Set environment variables
cp .env.example .env
# Edit .env with your API keys

# Run locally
python -m src.main
```

### Google Cloud Deployment

```bash
# Authenticate
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Deploy to Cloud Run
./scripts/deploy.sh
```

## Project Structure

```
aegis-ui-agent/
├── src/
│   ├── main.py              # FastAPI app entrypoint
│   ├── agent/
│   │   ├── orchestrator.py  # ADK agent orchestration
│   │   ├── navigator.py     # Core UI navigation logic
│   │   ├── analyzer.py      # Screenshot analysis with Gemini vision
│   │   └── executor.py      # Playwright action execution
│   ├── live/
│   │   ├── session.py       # Live API session management
│   │   └── voice.py         # Voice interaction handler
│   ├── tools/
│   │   ├── screenshot.py    # Screen capture utilities
│   │   ├── browser.py       # Browser management
│   │   └── actions.py       # Action primitives (click, type, scroll)
│   └── utils/
│       ├── config.py        # Configuration
│       └── logging.py       # Structured logging
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Main React app
│   │   ├── components/
│   │   │   ├── VoiceControl.tsx
│   │   │   ├── ScreenView.tsx
│   │   │   └── ActionLog.tsx
│   │   └── hooks/
│   │       └── useLiveAPI.ts
│   └── package.json
├── tests/
├── scripts/
│   ├── deploy.sh            # Cloud Run deployment
│   └── setup_gcp.sh         # GCP project setup
├── Dockerfile
├── cloudbuild.yaml
├── requirements.txt
├── .env.example
└── README.md
```

## How It Works

1. **User speaks or types** a natural language instruction (e.g., "Go to Amazon and search for wireless headphones under $50")
2. **Live API** processes voice input in real-time and streams it to the agent
3. **ADK Orchestrator** breaks the task into steps and delegates to the Navigator
4. **Screenshot Analyzer** captures the current browser state and uses Gemini vision to understand the UI layout
5. **Action Executor** performs the identified action (click, type, scroll, etc.) via Playwright
6. **Loop** — capture new screenshot → analyze → act → repeat until task is complete
7. **Agent narrates** progress back to user via Live API voice output

## License

MIT
