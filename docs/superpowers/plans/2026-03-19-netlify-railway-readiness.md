# Netlify + Railway Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the super-admin seed flow reliable and prepare the app for a split deployment with the frontend on Netlify and the backend on Railway.

**Architecture:** Keep the backend on FastAPI/Railway and the public frontend on Netlify, but make auth/session handling configurable for split-domain deployments. Production config should support both the recommended `api.mohex.org` custom backend domain and the fallback Railway-generated domain.

**Tech Stack:** FastAPI, SQLAlchemy async, Vite/React, Railway, Netlify, pytest

---

### Task 1: Deployment-Safe Auth Session Settings

**Files:**
- Modify: `config.py`
- Modify: `auth.py`
- Modify: `main.py`
- Test: `tests/test_auth_deploy_config.py`

- [ ] **Step 1: Write the failing tests**

Add tests covering:
- public base URL resolution from explicit `PUBLIC_BASE_URL`
- fallback resolution from `RAILWAY_PUBLIC_DOMAIN`
- cookie `samesite` behavior for configurable split deploys

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth_deploy_config.py -q`
Expected: FAIL because the settings helpers/configurable cookie policy do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add:
- `COOKIE_SAMESITE`
- optional `COOKIE_DOMAIN`
- helper for resolved public base URL
- helper for normalized frontend URL

Use these helpers in auth cookie issuance, OAuth callback generation, and `SessionMiddleware`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth_deploy_config.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config.py auth.py main.py tests/test_auth_deploy_config.py
git commit -m "fix: make auth config deployment-safe for split domains"
```

### Task 2: Deployment Config And Frontend Runtime Cleanup

**Files:**
- Modify: `.env.example`
- Modify: `frontend/.env.example`
- Modify: `docs-site/.env.example`
- Modify: `netlify.toml`
- Modify: `README.md`

- [ ] **Step 1: Write the failing/coverage checks**

Decide the expected documented production values:
- frontend domain `https://mohex.org`
- recommended backend domain `https://api.mohex.org`
- Railway fallback domain `https://<service>.up.railway.app`

- [ ] **Step 2: Update deploy config**

Document and/or set:
- `FRONTEND_URL`
- `PUBLIC_BASE_URL`
- `CORS_ORIGINS`
- `COOKIE_SECURE`
- `COOKIE_SAMESITE`
- frontend `VITE_API_URL`
- frontend `VITE_WS_URL`
- OAuth callback URLs

- [ ] **Step 3: Verify docs/config consistency**

Run: `rg -n "COOKIE_SAMESITE|PUBLIC_BASE_URL|FRONTEND_URL|VITE_API_URL|VITE_WS_URL|callback" .env.example README.md frontend/.env.example docs-site/.env.example netlify.toml`
Expected: consistent production guidance with no stale localhost-only deploy instructions.

- [ ] **Step 4: Commit**

```bash
git add .env.example frontend/.env.example docs-site/.env.example netlify.toml README.md
git commit -m "docs: prepare netlify and railway deployment config"
```

### Task 3: Script + Live Verification

**Files:**
- Modify: `scripts/seed_super_admin.py` if needed
- Modify: `ONBOARDING.md`

- [ ] **Step 1: Run targeted tests**

Run:
- `pytest tests/test_seed_super_admin.py -q`
- `pytest tests/test_database_readiness.py -q`

Expected: PASS

- [ ] **Step 2: Run live verification**

Run:
- `python scripts/seed_super_admin.py --email admin@mohex.org --password "ChangeThis123!" --name "Mohex Super Admin"`
- start backend and verify `/health` reaches `database=ready`
- verify `POST /api/auth/password/signup` succeeds after readiness

- [ ] **Step 3: Update onboarding**

Record:
- why the script previously failed
- what changed for deployment readiness
- exact next deployment steps for Railway and Netlify

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_super_admin.py ONBOARDING.md
git commit -m "chore: verify superadmin seed and deploy readiness"
```
