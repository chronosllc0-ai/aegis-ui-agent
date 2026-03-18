# Codex Task: Aegis Admin System

## Context
Aegis is a FastAPI + React/TypeScript app. The backend is at the repo root (`main.py`, `auth.py`, `config.py`, `backend/`). The frontend is at `frontend/` (Vite + React + TypeScript + Tailwind v4). The app uses SQLAlchemy async with PostgreSQL (asyncpg) and falls back to SQLite for local dev. Auth uses HMAC-signed session cookies (`aegis_session`).

**CRITICAL RULES:**
- Do NOT use emojis as icons anywhere. Use react-icons (`react-icons/fa`, `react-icons/lu`, `react-icons/si`) for all icons.
- Do NOT break existing features. All current routes, WebSocket behavior, auth flows, settings, BYOK, credit system, and landing page must continue working.
- The frontend uses Tailwind v4 with a dark theme (`bg-[#111]`, `bg-[#1a1a1a]`, `border-[#2a2a2a]`, `text-zinc-*`). Match this exact style.
- Use the existing pattern: `apiUrl('/path')` from `frontend/src/lib/api.ts` for all API calls.
- The existing `Icons` object in `frontend/src/components/icons.tsx` uses inline SVGs for some icons and react-icons for others. Use react-icons from `lu` (Lucide) or `fa` (Font Awesome) for new icons. Import them directly where needed.
- ESLint is strict: no setState in useEffect bodies (use derived state or refs), no ref access during render. Follow the patterns in existing hooks like `useUsage.ts`.

## What to implement

### Phase 1: Database + Auth Foundation

#### 1a. Modify `backend/database.py`

Add to `User` model:
```python
role = Column(String(20), default="user")      # "user" | "admin" | "superadmin"
status = Column(String(20), default="active")   # "active" | "suspended" | "banned"
```

Add these new models:

```python
class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    platform = Column(String(50), nullable=False)      # "web" | "telegram" | "slack" | "discord"
    platform_chat_id = Column(String(255))
    title = Column(String(500))
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    conversation_id = Column(String(255), nullable=False, index=True)
    role = Column(String(20), nullable=False)           # "user" | "assistant" | "system"
    content = Column(Text, nullable=False)
    platform_message_id = Column(String(255))
    metadata_json = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PaymentMethod(Base):
    __tablename__ = "payment_methods"
    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    stripe_customer_id = Column(String(255))
    stripe_payment_method_id = Column(String(255))
    type = Column(String(30))                           # "card" | "bank"
    brand = Column(String(30))
    last4 = Column(String(4))
    exp_month = Column(Integer)
    exp_year = Column(Integer)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    admin_id = Column(String(255), nullable=False, index=True)
    action = Column(String(100), nullable=False)
    target_user_id = Column(String(255), index=True)
    details_json = Column(Text)
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

class ImpersonationSession(Base):
    __tablename__ = "impersonation_sessions"
    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    admin_id = Column(String(255), nullable=False)
    target_user_id = Column(String(255), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text)
```

Add `Boolean` to the imports from sqlalchemy. Update `_ensure_user_columns_sync` to also add `role` and `status` columns if missing.

#### 1b. Modify `config.py`

Add:
```python
ADMIN_EMAILS: str = ""  # comma-separated emails that get admin role on first login
ADMIN_SESSION_TTL_SECONDS: int = 3600
```

#### 1c. Modify `auth.py`

In `_upsert_user()`:
- After creating a new user, check if their email is in `settings.ADMIN_EMAILS`. If yes, set `role = "admin"`.
- Include `role` and `status` in the returned payload dict.
- If `existing.status != "active"`, raise `HTTPException(403, "Account suspended")`.

In `_sign_session()`:
- The payload already includes whatever dict is passed. No changes needed — just ensure `role` is in the dict passed to it.

In `me()` endpoint:
- The session payload already includes role (since `_upsert_user` now returns it). No changes needed.

#### 1d. Create `backend/admin/__init__.py`

```python
from .router import router as admin_router
```

#### 1e. Create `backend/admin/dependencies.py`

```python
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import User, get_session
from auth import _verify_session

async def get_admin_user(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db_user = await session.get(User, payload["uid"])
    if not db_user or db_user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    if db_user.status != "active":
        raise HTTPException(status_code=403, detail="Account suspended")
    return {**payload, "role": db_user.role, "db_user": db_user}

async def require_superadmin(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    admin = await get_admin_user(request, session)
    if admin["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return admin
```

#### 1f. Create `backend/admin/audit_service.py`

```python
import json
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import AuditLog

async def log_admin_action(
    session: AsyncSession,
    admin_id: str,
    action: str,
    target_user_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    entry = AuditLog(
        admin_id=admin_id,
        action=action,
        target_user_id=target_user_id,
        details_json=json.dumps(details) if details else None,
        ip_address=ip_address,
    )
    session.add(entry)
    await session.commit()
```

### Phase 2: Admin API Endpoints

#### 2a. Create `backend/admin/dashboard.py`

`GET /dashboard` — returns:
- `total_users` (count of users)
- `active_users` (last_login_at within 7 days)
- `new_users_this_month`
- `total_credits_used` (sum across all UsageEvents this month)
- `active_conversations` (conversations with status="active")
- `platform_breakdown` (count of conversations per platform)

#### 2b. Create `backend/admin/users.py`

Endpoints:
- `GET /` — list users with query params: `search` (email/name), `role`, `status`, `plan`, `sort_by`, `sort_dir`, `limit`, `offset`
- `GET /{uid}` — full user detail including credit balance, usage summary, conversation count, payment methods
- `PUT /{uid}` — update user fields (name, email, role, status). Only superadmin can change role.
- `POST /{uid}/suspend` — set status="suspended", log audit
- `POST /{uid}/reinstate` — set status="active", log audit
- `POST /{uid}/credit-adjustment` — body: `{amount: int, reason: str}` — add or subtract credits

#### 2c. Create `backend/admin/billing.py`

Endpoints:
- `GET /users/{uid}/payment-methods` — list payment methods for a user
- `POST /users/{uid}/payment-methods` — add payment method (fields: type, brand, last4, exp_month, exp_year; no real Stripe integration yet, just store the record)
- `PUT /users/{uid}/payment-methods/{pm_id}/default` — set as default
- `DELETE /users/{uid}/payment-methods/{pm_id}` — remove
- `PUT /users/{uid}/plan` — body: `{plan: str, monthly_allowance: int}` — update plan on CreditBalance

#### 2d. Create `backend/admin/conversations.py`

Endpoints:
- `GET /` — list conversations with filters: `user_id`, `platform`, `status`, `search` (title), `limit`, `offset`
- `GET /{conversation_id}` — full conversation with messages (paginated)
- `GET /user/{uid}` — all conversations for a specific user
- `GET /stats` — per-platform conversation counts, message counts, active users per platform

#### 2e. Create `backend/admin/impersonation.py`

Endpoints:
- `POST /start` — body: `{target: str}` (email or uid). Look up user, create ImpersonationSession, set `aegis_admin_session` cookie (preserve admin session), issue new `aegis_session` as target user with `impersonating: true` and `admin_uid` in payload. Log audit.
- `POST /stop` — restore admin session from `aegis_admin_session`, delete `aegis_admin_session`, update ImpersonationSession.ended_at. Log audit.
- `GET /status` — check if currently impersonating (check for `impersonating` in session payload)

#### 2f. Create `backend/admin/audit.py`

Endpoints:
- `GET /` — paginated audit log with filters: `admin_id`, `action`, `target_user_id`, `date_from`, `date_to`, `limit`, `offset`

#### 2g. Create `backend/admin/router.py`

Mount all sub-routers under `/api/admin`:
```python
from fastapi import APIRouter
from . import dashboard, users, billing, conversations, impersonation, audit

router = APIRouter(prefix="/api/admin", tags=["admin"])
router.include_router(dashboard.router, prefix="/dashboard")
router.include_router(users.router, prefix="/users")
router.include_router(billing.router, prefix="/billing")
router.include_router(conversations.router, prefix="/conversations")
router.include_router(impersonation.router, prefix="/impersonate")
router.include_router(audit.router, prefix="/audit")
```

#### 2h. Modify `main.py`

Add near the top with other imports:
```python
from backend.admin import admin_router
```

Add after `app.include_router(auth_router)`:
```python
app.include_router(admin_router)
```

### Phase 3: Conversation Persistence

#### 3a. Create `backend/conversation_service.py`

Functions:
```python
async def get_or_create_conversation(session, user_id, platform, platform_chat_id=None) -> Conversation
async def append_message(session, conversation_id, role, content, metadata=None, platform_message_id=None) -> ConversationMessage
async def update_conversation_title(session, conversation_id, title)
```

#### 3b. Wire into WebSocket handler in `main.py`

In `websocket_navigate`:
- After the first "navigate" action, create a conversation: `conversation = await get_or_create_conversation(db_session, user_uid, "web", session_id)`
- In `_run_navigation_task`, after getting result, append messages for the instruction and result.
- This requires getting a DB session inside the WebSocket handler — use `_session_factory()` directly (not Depends, since it's a WebSocket).

#### 3c. Wire into integration webhooks

In `telegram_webhook`, `slack_send_message`, `discord_send_message` — after processing, append messages to conversations.

### Phase 4: Frontend — React Router + Admin Panel

#### 4a. Install react-router-dom

Add to `frontend/package.json` dependencies: `"react-router-dom": "^7.4.0"`

#### 4b. Refactor `frontend/src/main.tsx`

Wrap `<App />` with `<BrowserRouter>`.

#### 4c. Refactor `frontend/src/App.tsx`

Replace the current state-based view switching with React Router:

```tsx
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'

function App() {
  // Keep existing auth check logic
  // ...

  if (authLoading) return <LoadingScreen />

  return (
    <Routes>
      <Route path="/" element={!isAuthenticated ? <LandingPage onGetStarted={() => navigate('/auth')} /> : <Navigate to={authUser?.role === 'admin' || authUser?.role === 'superadmin' ? '/admin' : '/app'} />} />
      <Route path="/auth" element={!isAuthenticated ? <AuthPage onAuthenticated={handleAuth} /> : <Navigate to="/app" />} />
      <Route path="/app/*" element={isAuthenticated ? <ClientDashboard ... /> : <Navigate to="/auth" />} />
      <Route path="/admin/*" element={isAuthenticated && (authUser?.role === 'admin' || authUser?.role === 'superadmin') ? <AdminLayout ... /> : <Navigate to="/app" />} />
    </Routes>
  )
}
```

Extract the current authenticated main view into a `<ClientDashboard>` component (it's everything currently inside the `return` block when `isAuthenticated` is true). This is a pure extraction — no logic changes.

**IMPORTANT**: The existing client dashboard must work exactly as before. All WebSocket, InputBar, ScreenView, ActionLog, settings, usage, etc. functionality must be preserved.

#### 4d. Create `frontend/src/admin/AdminLayout.tsx`

The admin layout has:
1. **Collapsible left sidebar** — slides in/out independently. Contains nav links with react-icons (NOT emojis).
2. **Main content area** — renders the active page
3. **Slide-out detail panel** — slides from the right edge, used for user detail, conversation viewer, etc. Can be open while sidebar is in any state.

```tsx
// Sidebar nav items (use react-icons from 'lu'):
// LuLayoutDashboard → Dashboard
// LuUsers → Users
// LuCreditCard → Billing
// LuMessageSquare → Conversations
// LuBot → Agents
// LuShield → Audit Log
// LuSettings → Settings
// LuArrowLeftRight → Switch to App
```

Style: Same dark theme as client. Sidebar: `bg-[#171717] border-[#2a2a2a]`. Main: `bg-[#111]`. Active nav: `bg-blue-600`.

The sidebar should have a toggle button. On mobile, overlay with backdrop. On desktop, it pushes the main content.

The detail panel slides from the right with a semi-transparent backdrop. It's 400-500px wide and scrollable.

#### 4e. Create admin pages

All pages in `frontend/src/admin/pages/`:

**DashboardPage.tsx:**
- Grid of stat cards: Total Users, Active Users, New This Month, Credits Used, Active Conversations
- Each card: icon + label + number, dark card style (`bg-[#1a1a1a] border-[#2a2a2a]`)
- Recent activity list (from audit log)
- Platform breakdown bar chart (simple div-based, no chart library needed)

**UsersPage.tsx:**
- Search bar + role filter dropdown + status filter dropdown
- Table with columns: Name, Email, Role, Plan, Status, Last Login, Actions
- Row click opens UserDetailPanel in the slide-out detail panel
- Quick action buttons per row: Suspend/Reinstate, View as User (impersonate)
- Pagination controls at bottom

**UserDetailPanel.tsx** (renders inside the right slide-out panel):
- Header: avatar, name, email, role badge, status badge
- Tabs: Overview | Billing | Conversations | Usage
- Overview: basic info, plan, credits, last login, created date. Edit button for name/email/role.
- Billing: list payment methods, add/remove, set default. Plan selector (Free/Pro/Team) with save.
- Conversations: list of conversations with platform badge, click to view
- Usage: credit balance, usage chart, recent events
- Bottom: "View as User" button (impersonation), "Suspend" button

**ConversationsPage.tsx:**
- Filters: platform dropdown (All/Web/Telegram/Slack/Discord), user search, date range
- List of conversations: user avatar+name, platform badge, title/preview, message count, last activity
- Click opens conversation in detail panel

**ConversationViewer.tsx** (in detail panel):
- Header: platform badge, user info, conversation title, date
- Chat-style message list: user messages on right (blue), assistant on left (gray), system messages centered
- Scroll to bottom, load more at top
- Message metadata on hover: timestamp, tokens, model used

**AuditPage.tsx:**
- Filters: admin (dropdown), action type (dropdown), target user (search), date range
- Table: Timestamp, Admin, Action, Target User, Details, IP
- Expandable detail row for JSON details

**BillingPage.tsx:**
- Overview stats: total revenue, active paying users, MRR
- Recent transactions table
- Quick search to find user billing

**AdminSettingsPage.tsx:**
- Global defaults: default model, default system instruction, default temperature
- Admin management: list of admins/superadmins (superadmin only can promote/demote)
- Add admin by email input

#### 4f. Create `frontend/src/admin/components/ImpersonationBanner.tsx`

Fixed bar at the very top of the page when `impersonating: true` in auth session:
- Yellow/amber background (`bg-amber-500/10 border-amber-500/30`)
- Text: "You are viewing as [user email]"
- "Exit" button that calls `POST /api/admin/impersonate/stop` and reloads

This banner should appear on BOTH admin and client views when impersonating.

#### 4g. Create admin hooks in `frontend/src/admin/hooks/`

Each hook follows the pattern of existing hooks (like `useUsage.ts`):
- `useAdminUsers.ts` — `fetchUsers(params)`, `fetchUser(uid)`, `updateUser(uid, data)`, etc.
- `useAdminBilling.ts` — payment method CRUD
- `useAdminConversations.ts` — fetch/search conversations
- `useAdminAudit.ts` — fetch audit logs
- `useAdminDashboard.ts` — fetch dashboard stats
- `useImpersonation.ts` — start/stop/check impersonation status

### Phase 5: Impersonation Integration

In `frontend/src/App.tsx` (or the root component):
- On `GET /api/auth/me`, check if `user.impersonating === true`
- If yes, pass that state down or use context
- Render `ImpersonationBanner` at the top of the layout

When impersonating and on the `/app` route:
- Everything works as the target user — their settings, their conversations, their keys
- The admin can navigate, test, diagnose issues from the user's perspective
- Every action is still logged in the audit trail on the backend

## Files to NOT modify (leave as-is)
- `orchestrator.py` — leave Gemini orchestrator as-is for now
- `session.py` — leave Live session manager as-is
- `navigator.py` — leave navigator as-is
- `analyzer.py` — leave analyzer as-is
- `executor.py` — leave executor as-is
- `mcp_client.py` — leave MCP client as-is
- `backend/providers/*` — leave all provider adapters as-is
- `backend/credit_rates.py` — leave credit rates as-is
- `backend/credit_service.py` — leave credit service as-is
- `backend/key_management.py` — leave key management as-is
- `frontend/src/components/LandingPage.tsx` — leave landing page as-is
- `frontend/src/components/InputBar.tsx` — leave input bar as-is
- `frontend/src/components/ScreenView.tsx` — leave screen view as-is
- `frontend/src/components/ActionLog.tsx` — leave action log as-is
- `frontend/src/components/WorkflowView.tsx` — leave workflow view as-is
- `frontend/src/hooks/useMicrophone.ts` — leave microphone hook as-is
- `frontend/src/hooks/useSettings.ts` — leave settings hook as-is (except adding `role` to auth user type if needed)
- `frontend/src/lib/models.ts` — leave model catalog as-is
- `frontend/src/lib/creditRates.ts` — leave credit rates as-is

## Verification checklist
After implementation, verify:
1. `cd frontend && npm run build` succeeds with zero errors
2. `cd frontend && npm run lint` passes with zero errors
3. Existing auth flows (Google OAuth, GitHub OAuth, email/password signup+login) still work
4. Existing WebSocket navigation still works
5. Existing settings page (Profile, Agent, API Keys, Usage, Integrations, Workflows tabs) still works
6. Landing page still renders correctly
7. Admin routes are only accessible with admin/superadmin role
8. Client routes still work for regular users
9. No emojis used as icons anywhere — only react-icons components
