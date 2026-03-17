# Aegis — AI-Powered Universal UI Agent

**Aegis** by Chronos is an autonomous agent that sees your screen, understands intent, and
interacts with any web UI using multimodal vision and real-time browser automation.

> Production-ready at **[mohex.org](https://mohex.org)** · Docs coming soon

---

## Features

| Feature | Description |
|---|---|
| 🌐 **Multi-model** | OpenAI (GPT-4.1), Anthropic (Claude 4), Google (Gemini 3), Mistral, Groq — swap mid-session |
| 🔑 **BYOK** | Bring Your Own Key — encrypted at rest with AES-256; billed to your provider account |
| 🎙️ **Voice control** | Real-time voice steering via Live API |
| 🧠 **Vision-first** | Multimodal screenshots → reasoning → Playwright actions |
| ⚡ **Real-time** | WebSocket streams of actions, frames, and logs |
| 🔗 **Integrations** | Telegram, Slack, and Discord connectors for agent delegation |
| 🚀 **Railway-ready** | One-click deploy to Railway with PostgreSQL |

## Tech Stack

- **Frontend**: React + TypeScript + Vite + Tailwind v4
- **Backend**: FastAPI + WebSockets + Playwright
- **Database**: PostgreSQL (async via SQLAlchemy + asyncpg)
- **LLM SDK**: `openai`, `anthropic`, `google-genai`, `mistralai`, `groq`
- **Deploy**: Docker, Railway, docker-compose

## Quick Start

### 1. Docker Compose (recommended)

```bash
cp .env.example .env          # fill in at least one LLM key
docker compose up -d           # starts postgres + app
open http://localhost:8000
```

### 2. Local development

```bash
# Backend
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
uvicorn main:app --reload

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

### 3. Railway

```bash
npm i -g @railway/cli
railway login
railway link
railway up
```

Add a PostgreSQL plugin from the Railway dashboard, then set `SESSION_SECRET`,
`ENCRYPTION_SECRET`, and at least one LLM API key in environment variables.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes (prod) | PostgreSQL connection string |
| `SESSION_SECRET` | Yes | Random string for session signing |
| `ENCRYPTION_SECRET` | Yes | Secret for BYOK key encryption |
| `GEMINI_API_KEY` | No | Default Gemini API key |
| `OPENAI_API_KEY` | No | Default OpenAI API key |
| `ANTHROPIC_API_KEY` | No | Default Anthropic API key |
| `MISTRAL_API_KEY` | No | Default Mistral API key |
| `GROQ_API_KEY` | No | Default Groq API key |

See `.env.example` for the full list.

## Architecture

```
┌──────────────┐   WS    ┌───────────────┐
│  React       │ ◄─────► │  FastAPI       │
│  Frontend    │         │  main.py       │
└──────────────┘         └─────┬─────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
      ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
      │ Orchestrator │ │ Providers    │ │ Key Manager  │
      │ (Analyzer +  │ │ (OpenAI,     │ │ (AES-256     │
      │  Executor +  │ │  Anthropic,  │ │  encrypted)  │
      │  Navigator)  │ │  Gemini, …)  │ └──────────────┘
      └──────┬───────┘ └──────────────┘
             ▼
      ┌──────────────┐
      │ Playwright   │
      │ (Browser)    │
      └──────────────┘
```

## License

Proprietary — © 2024-2026 Chronos Intelligence Systems
