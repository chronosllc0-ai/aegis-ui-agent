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
| 💳 **Credit system** | Per-model cost tracking, usage dashboard, spending caps |
| 🚀 **Deploy anywhere** | Railway (full-stack), Netlify (frontend) + Railway (API), Docker |

## Tech Stack

- **Frontend**: React + TypeScript + Vite + Tailwind v4
- **Backend**: FastAPI + WebSockets + Playwright
- **Database**: PostgreSQL (async via SQLAlchemy + asyncpg)
- **LLM SDK**: `openai`, `anthropic`, `google-genai`, `mistralai`, `groq`
- **Deploy**: Docker, Railway, Netlify, docker-compose

---

## Quick Start

### 1. Docker Compose (recommended for local dev)

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

---

## Deploy to Netlify (Frontend)

Netlify hosts the React frontend as a static site. The FastAPI backend runs
separately on Railway (or any server that supports WebSockets + Docker).

### Step 1 — Deploy the backend to Railway

```bash
npm i -g @railway/cli
railway login
railway link          # link this repo
railway up            # deploys from Dockerfile
```

Add a PostgreSQL plugin from the Railway dashboard, then set these env vars:

| Variable | Value |
|---|---|
| `SESSION_SECRET` | Random 32+ char string |
| `ENCRYPTION_SECRET` | Random 32+ char string |
| `ADMIN_EMAILS` | Comma-separated email list for auto-admin assignment |
| `FRONTEND_URL` | `https://mohex.org` |
| `PUBLIC_BASE_URL` | `https://api.mohex.org` (recommended) or your Railway URL |
| `CORS_ORIGINS` | `https://mohex.org,https://www.mohex.org` |
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAMESITE` | `lax` with `api.mohex.org`, or `none` if you keep the Railway URL |
| `GEMINI_API_KEY` | (or any provider key) |

Recommended production topology:

- Frontend: `https://mohex.org`
- Backend: `https://api.mohex.org`

Railway fallback topology:

- Frontend: `https://mohex.org`
- Backend: `https://your-service.up.railway.app`

OAuth callback URLs are derived from `PUBLIC_BASE_URL`:

- Google: `https://<backend-origin>/api/auth/google/callback`
- GitHub: `https://<backend-origin>/api/auth/github/callback`
- SSO: `https://<backend-origin>/api/auth/sso/callback`

### Step 2 — Deploy the frontend to Netlify

#### Option A: Netlify Dashboard (easiest)

1. Go to [app.netlify.com](https://app.netlify.com) → **Add new site** → **Import an existing project**
2. Connect your GitHub repo (`chronosllc0-ai/aegis-ui-agent`)
3. Netlify auto-detects settings from `netlify.toml`:
   - **Base directory**: `frontend`
   - **Build command**: `npm ci && npm run build`
   - **Publish directory**: `frontend/dist`
4. Set environment variables in **Site configuration → Environment variables**:

   | Variable | Value |
   |---|---|
   | `VITE_API_URL` | `https://api.mohex.org` |
   | `VITE_WS_URL` | `wss://api.mohex.org/ws/navigate` |
   | `VITE_DOCS_SITE_URL` | `https://docs.mohex.org` |

5. Click **Deploy site**

#### Option B: Netlify CLI

```bash
# Install the CLI
npm i -g netlify-cli

# Login
netlify login

# Init (first time) — link to your Netlify account
netlify init
# Select "Create & configure a new site"
# The CLI reads netlify.toml automatically

# Set environment variables
netlify env:set VITE_API_URL https://api.mohex.org
netlify env:set VITE_WS_URL wss://api.mohex.org/ws/navigate
netlify env:set VITE_DOCS_SITE_URL https://docs.mohex.org

# Deploy (preview)
netlify deploy

# Deploy to production
netlify deploy --prod
```

#### Option C: Manual drag-and-drop

```bash
cd frontend
npm ci
VITE_API_URL=https://api.mohex.org \
VITE_WS_URL=wss://api.mohex.org/ws/navigate \
VITE_DOCS_SITE_URL=https://docs.mohex.org \
npm run build
```

Then drag the `frontend/dist/` folder into the Netlify dashboard deploy area.

### Step 3 — Custom domain (optional)

1. In Netlify dashboard → **Domain management** → **Add custom domain**
2. Add `mohex.org` for the frontend and `api.mohex.org` for the backend
3. Update DNS:
   - If using Netlify DNS: point nameservers to Netlify
   - If external DNS: add a CNAME record pointing to `your-site.netlify.app`
4. SSL is provisioned automatically

### Step 4 — Configure CORS on the backend

Since frontend (Netlify) and backend (Railway) are on different domains, make sure
the backend allows cross-origin requests. In your Railway environment variables:

| Variable | Value |
|---|---|
| `FRONTEND_URL` | `https://mohex.org` |
| `CORS_ORIGINS` | `https://mohex.org,https://www.mohex.org` |
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAMESITE` | `lax` when using `api.mohex.org`; `none` when using `*.up.railway.app` |

Using `api.mohex.org` is recommended because it keeps the frontend and backend on
the same site (`mohex.org`) and avoids cross-site auth-cookie issues.

### Continuous deployment

Once connected via GitHub, every push to `main` triggers:
- Netlify rebuilds the frontend automatically
- Railway rebuilds the backend automatically (if Railway is linked to the same repo)

### Architecture (Netlify + Railway)

```
┌─────────────────────────┐          ┌─────────────────────────┐
│  Netlify CDN            │   API    │  Railway                │
│  ┌───────────────────┐  │  ──────► │  ┌───────────────────┐  │
│  │ React SPA         │  │  HTTPS   │  │ FastAPI + WS      │  │
│  │ (static assets)   │  │          │  │ Playwright         │  │
│  └───────────────────┘  │  ◄────── │  │ PostgreSQL         │  │
│  mohex.org              │  WSS     │  └───────────────────┘  │
└─────────────────────────┘          └─────────────────────────┘
```

---

## Deploy to Railway (Full-Stack)

If you prefer a single-service deployment:

```bash
npm i -g @railway/cli
railway login
railway link
railway up
```

Add a PostgreSQL plugin from the Railway dashboard, then set `SESSION_SECRET`,
`ENCRYPTION_SECRET`, `ADMIN_EMAILS` (if you want auto-admin assignment), `PUBLIC_BASE_URL`,
`FRONTEND_URL`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, and at least one LLM API key in environment variables.

### Seed the first superadmin

After the backend is up, seed the first password-based superadmin:

```bash
python scripts/seed_super_admin.py --email admin@mohex.org --password "ChangeThis123!" --name "Mohex Super Admin"
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes (prod) | PostgreSQL connection string |
| `SESSION_SECRET` | Yes | Random string for session signing |
| `PUBLIC_BASE_URL` | Yes (prod) | Public backend origin used for OAuth callbacks |
| `FRONTEND_URL` | Yes (split deploy) | Frontend origin for redirects and CORS |
| `COOKIE_SECURE` | Yes (prod) | Must be `true` in production |
| `COOKIE_SAMESITE` | Depends | `lax` for `api.mohex.org`, `none` for Railway default domain split |
| `COOKIE_DOMAIN` | No | Optional explicit cookie domain override |
| `ADMIN_EMAILS` | No | Comma-separated email list for auto-admin assignment |
| `ENCRYPTION_SECRET` | Yes | Secret for BYOK key encryption |
| `GEMINI_API_KEY` | No | Default Gemini API key |
| `OPENAI_API_KEY` | No | Default OpenAI API key |
| `ANTHROPIC_API_KEY` | No | Default Anthropic API key |
| `MISTRAL_API_KEY` | No | Default Mistral API key |
| `GROQ_API_KEY` | No | Default Groq API key |
| `CORS_ORIGINS` | No | Comma-separated allowed frontend origins |
| `RAILWAY_PUBLIC_DOMAIN` | No | Railway-provided fallback domain if `PUBLIC_BASE_URL` is left blank |
| `VITE_API_URL` | Frontend | Backend URL (only when frontend is hosted separately) |
| `VITE_WS_URL` | Frontend | Backend WebSocket URL (only when hosted separately) |

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
      │ Orchestrator │ │ Providers    │ │ Credit System│
      │ (Analyzer +  │ │ (OpenAI,     │ │ (Rates +     │
      │  Executor +  │ │  Anthropic,  │ │  Balance +   │
      │  Navigator)  │ │  Gemini, …)  │ │  Usage)      │
      └──────┬───────┘ └──────────────┘ └──────────────┘
             ▼                                ▼
      ┌──────────────┐              ┌──────────────┐
      │ Playwright   │              │ Key Manager  │
      │ (Browser)    │              │ (AES-256     │
      └──────────────┘              │  encrypted)  │
                                    └──────────────┘
```

## License

Proprietary — © 2024-2026 Chronos Intelligence Systems
