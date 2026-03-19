# Admin System — Phases 2–5 Consolidated

> **One prompt to implement the full admin system**: backend API endpoints (Phase 2), conversation persistence (Phase 3), admin frontend panel (Phase 4), and impersonation + polish (Phase 5).
>
> Phase 1 is already done: `User.role`/`status` columns, all database models (`Conversation`, `ConversationMessage`, `PaymentMethod`, `AuditLog`, `ImpersonationSession`), `backend/admin/dependencies.py` (`get_admin_user`, `require_superadmin`), `backend/admin/audit_service.py` (`log_admin_action`), `backend/admin/dashboard.py` (dashboard stats), and the admin router mounted in `main.py`.

---

## CRITICAL RULES — read every one

1. **No emojis as icons.** Use `react-icons/lu` (Lucide) for all UI icons. Import directly: `import { LuUsers } from 'react-icons/lu'`
2. **Dark theme colors** — match exactly: `bg-[#111]` background, `bg-[#1a1a1a]` cards, `bg-[#171717]` sidebar, `border-[#2a2a2a]` borders, `text-zinc-*` text, `bg-blue-600` accent
3. **ESLint strict** — NO `setState` inside `useEffect` bodies, NO ref access during render. Use derived-state patterns or callbacks.
4. **Tailwind v4** — the frontend uses Tailwind v4. No `@apply` in JS, no `tailwind.config.js` changes.
5. **API calls** — use `apiUrl('/path')` from `frontend/src/lib/api.ts` for ALL fetch calls.
6. **Do NOT modify these files**: `orchestrator.py`, `session.py`, `navigator.py`, `analyzer.py`, `executor.py`, `backend/providers/*`, `backend/credit_rates.py`, `backend/credit_service.py`, `LandingPage.tsx`, `InputBar.tsx`, `ScreenView.tsx`, `ActionLog.tsx`, `WorkflowView.tsx`, `UsageMeterBar.tsx`, `CostEstimator.tsx`, `CreditBadge.tsx`, `SpendingAlert.tsx`, `useSettings.ts`, `useMicrophone.ts`, `useUsage.ts`, `useWebSocket.ts`, `models.ts`, `creditRates.ts`, `mcp.ts`, `icons.tsx`, anything in `components/settings/`
7. **All existing functionality must keep working** — WebSocket, InputBar, ScreenView, ActionLog, settings, usage, BYOK, landing page, auth.
8. **Python backend**: Python 3.11+, type hints everywhere, `from __future__ import annotations` at top of every new file.
9. **Verified react-icons/lu names** (some differ from docs): `LuLayoutDashboard`, `LuUsers`, `LuCreditCard`, `LuMessageSquare`, `LuBot`, `LuShield`, `LuSettings`, `LuSearch`, `LuChevronLeft`, `LuChevronRight`, `LuX`, `LuPanelLeftOpen`, `LuPanelLeftClose`, `LuTriangleAlert` (NOT `LuAlertTriangle`), `LuChartBar` (NOT `LuBarChart3`), `LuLoader` (NOT `LuLoader2`), `LuFilter`, `LuDownload`, `LuEye`, `LuPencil`, `LuBan`, `LuCheck`, `LuMoreVertical`, `LuArrowLeftRight`

---

## What already exists (do NOT recreate)

```
backend/admin/__init__.py          — exports admin_router
backend/admin/router.py            — mounts dashboard.router at /dashboard
backend/admin/dependencies.py      — get_admin_user, require_superadmin
backend/admin/audit_service.py     — log_admin_action (has bugs: fix them — see below)
backend/admin/dashboard.py         — GET /api/admin/dashboard/
backend/database.py                — All models: User, AuthCode, UserAPIKey, CreditBalance, UsageEvent,
                                     CreditTopUp, Conversation, ConversationMessage, PaymentMethod,
                                     AuditLog, ImpersonationSession
main.py line 22                    — from backend.admin import admin_router
main.py line 62                    — app.include_router(admin_router)
```

---

## Bug fix: `backend/admin/audit_service.py`

The current file has two bugs: duplicate `session.add()` and unreachable code after `return`. Fix it:

```python
"""Helpers for persisting admin audit records."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AuditLog


async def log_admin_action(
    session: AsyncSession,
    *,
    admin_id: str,
    action: str,
    target_user_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Insert and commit an immutable admin audit log entry."""
    audit_log = AuditLog(
        admin_id=admin_id,
        action=action,
        target_user_id=target_user_id,
        details_json=json.dumps(details) if details is not None else None,
        ip_address=ip_address,
    )
    session.add(audit_log)
    await session.commit()
    await session.refresh(audit_log)
    return audit_log
```

---

# PHASE 2 — Admin API Endpoints

All admin endpoints use `Depends(get_admin_user)`. Every state-changing action calls `log_admin_action()`. Use `request.client.host if request.client else None` for IP in audit logs.

## 2.1 Create `backend/admin/users.py`

```python
"""Admin user management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.audit_service import log_admin_action
from backend.admin.dependencies import get_admin_user, require_superadmin
from backend.database import (
    Conversation, CreditBalance, UsageEvent, User, get_session,
)

router = APIRouter()
```

Endpoints:

### `GET /` — List users
- Query params: `search` (str, match email or name via `ilike`), `role` (str), `status` (str), `sort_by` (str, default `"created_at"`), `sort_dir` (`"asc"` | `"desc"`, default `"desc"`), `limit` (int 1–200, default 50), `offset` (int ≥ 0, default 0)
- Returns `{ users: [...], total: int, limit, offset }`
- Each user: `uid, email, name, role, status, avatar_url, created_at, last_login_at`

### `GET /{uid}` — Full user detail
- Returns user fields + `credit_balance` (from CreditBalance: plan, monthly_allowance, credits_used, overage_credits) + `conversation_count` (count of Conversations for this user) + `total_credits_used` (sum of UsageEvent.credits_charged)
- 404 if not found

### `PUT /{uid}` — Update user
- Body: `{ name?, email? }` (no role — that's separate)
- Audit: `"user.update"` with before/after
- Returns updated user

### `PUT /{uid}/role` — Change role (superadmin only)
- Use `Depends(require_superadmin)` on this endpoint
- Body: `{ role: str }` — must be one of `"user"`, `"admin"`, `"superadmin"`
- Audit: `"user.role_change"` with old_role and new_role
- Returns updated user

### `POST /{uid}/suspend` — Suspend user
- Set `user.status = "suspended"`, audit `"user.suspend"`
- Returns updated user

### `POST /{uid}/reinstate` — Reinstate user
- Set `user.status = "active"`, audit `"user.reinstate"`
- Returns updated user

### `POST /{uid}/credit-adjustment` — Adjust credits
- Body: `{ amount: int, reason: str }` — positive = add, negative = remove
- Adjust `CreditBalance.credits_used` (decrease credits_used by amount to add credits, increase to remove)
- If no CreditBalance exists, create one with plan="free", monthly_allowance=1000
- Audit: `"billing.credit_adjustment"` with amount and reason
- Returns updated balance

## 2.2 Create `backend/admin/billing.py`

```python
"""Admin billing management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.audit_service import log_admin_action
from backend.admin.dependencies import get_admin_user
from backend.database import CreditBalance, PaymentMethod, User, get_session

router = APIRouter()
```

### `GET /users/{uid}/payment-methods` — List payment methods
### `POST /users/{uid}/payment-methods` — Add payment method
- Body: `{ type, brand, last4, exp_month, exp_year }`
- Audit: `"billing.add_payment_method"`

### `PUT /users/{uid}/payment-methods/{pm_id}/default` — Set default
- Unset all `is_default` for user, then set this one
- Audit: `"billing.set_default_payment"`

### `DELETE /users/{uid}/payment-methods/{pm_id}` — Remove
- Audit: `"billing.remove_payment_method"`

### `PUT /users/{uid}/plan` — Change plan
- Body: `{ plan: str, monthly_allowance: int }`
- Update or create CreditBalance
- Audit: `"billing.change_plan"` with old/new plan

## 2.3 Create `backend/admin/conversations.py`

```python
"""Admin conversation access endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.dependencies import get_admin_user
from backend.database import Conversation, ConversationMessage, User, get_session

router = APIRouter()
```

### `GET /` — List conversations
- Query params: `user_id`, `platform`, `status`, `search` (title ilike), `limit` (default 50), `offset`
- Returns `{ conversations: [...], total }` — each with: id, user_id, platform, title, status, message_count (subquery count), created_at, updated_at

### `GET /{conversation_id}` — Conversation with messages
- Query params: `limit` (default 100), `offset`
- Returns conversation fields + `messages` array (id, role, content, created_at, metadata parsed from metadata_json)
- 404 if not found

### `GET /user/{uid}` — Conversations for a user
- Same format as list, filtered by user_id

### `GET /stats` — Platform statistics
- Returns per-platform: conversation_count, message_count, unique_users

## 2.4 Create `backend/admin/impersonation.py`

```python
"""Admin user impersonation endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _sign_session, _verify_session
from backend.admin.audit_service import log_admin_action
from backend.admin.dependencies import get_admin_user
from backend.database import ImpersonationSession, User, get_session
from config import settings

router = APIRouter()
```

### `POST /start` — Start impersonation
- Body: `{ target: str }` — email or uid
- Look up user by email first, then by uid. 404 if not found.
- Cannot impersonate superadmins (403)
- Cannot impersonate yourself (400)
- Create `ImpersonationSession` record
- Set `aegis_admin_session` cookie = current `aegis_session` cookie value (preserve admin session)
- Issue new `aegis_session` cookie as the target user with extra fields: `"impersonating": True, "admin_uid": admin.uid`
- Use `_sign_session()` to create the token. Set the cookie with same params as `auth.py`'s `_session_response`:
  ```python
  response = JSONResponse({"ok": True, "target_user": {"uid": target.uid, "email": target.email, "name": target.name}})
  token = _sign_session({"uid": target.uid, "email": target.email, "name": target.name, "impersonating": True, "admin_uid": admin.uid})
  response.set_cookie("aegis_session", token, max_age=int(settings.SESSION_TTL_SECONDS), httponly=True, secure=bool(settings.COOKIE_SECURE), samesite="lax", path="/")
  response.set_cookie("aegis_admin_session", request.cookies.get("aegis_session", ""), max_age=int(settings.SESSION_TTL_SECONDS), httponly=True, secure=bool(settings.COOKIE_SECURE), samesite="lax", path="/")
  ```
- Audit: `"impersonate.start"`

### `POST /stop` — Stop impersonation
- Read `aegis_admin_session` cookie. Verify it. If invalid, 400.
- Restore as `aegis_session`. Delete `aegis_admin_session`.
- Find open ImpersonationSession (ended_at is null, admin_id = admin uid from restored session), set ended_at.
- Audit: `"impersonate.stop"`
- Return `{ ok: true }`

### `GET /status` — Check impersonation state
- Read current `aegis_session`, verify, check for `"impersonating"` field.
- Return `{ impersonating: bool, target_user?: {uid, email, name}, admin_uid?: str }`

## 2.5 Create `backend/admin/audit.py`

```python
"""Admin audit log viewing."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.dependencies import get_admin_user
from backend.database import AuditLog, get_session

router = APIRouter()
```

### `GET /` — Paginated audit log
- Query params: `admin_id`, `action`, `target_user_id`, `date_from` (ISO string), `date_to` (ISO string), `limit` (default 50), `offset`
- Returns `{ entries: [...], total }` — each: id, admin_id, action, target_user_id, details (parsed JSON), ip_address, created_at

## 2.6 Update `backend/admin/router.py`

Replace the current file with:

```python
"""Admin API router — mounts all admin sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from . import audit, billing, conversations, dashboard, impersonation, users

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_router.include_router(dashboard.router, prefix="/dashboard")
admin_router.include_router(users.router, prefix="/users")
admin_router.include_router(billing.router, prefix="/billing")
admin_router.include_router(conversations.router, prefix="/conversations")
admin_router.include_router(impersonation.router, prefix="/impersonate")
admin_router.include_router(audit.router, prefix="/audit")
```

---

# PHASE 3 — Conversation Persistence

Wire conversation logging into the WebSocket handler and integration webhooks. All logging is fire-and-forget — a database error must NEVER break the user's session or WebSocket.

## 3.1 Create `backend/conversation_service.py`

```python
"""Conversation persistence service.

All functions are fire-and-forget safe — failures are logged but never raised.
"""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Conversation, ConversationMessage

logger = logging.getLogger(__name__)


async def get_or_create_conversation(
    session: AsyncSession,
    user_id: str,
    platform: str,
    platform_chat_id: str | None = None,
    title: str | None = None,
) -> Conversation:
    """Find an active conversation or create one."""
    query = (
        select(Conversation)
        .where(Conversation.user_id == user_id, Conversation.platform == platform, Conversation.status == "active")
    )
    if platform_chat_id:
        query = query.where(Conversation.platform_chat_id == platform_chat_id)
    query = query.order_by(Conversation.created_at.desc()).limit(1)
    result = await session.execute(query)
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    conversation = Conversation(
        id=str(uuid4()),
        user_id=user_id,
        platform=platform,
        platform_chat_id=platform_chat_id,
        title=title or f"New {platform} conversation",
        status="active",
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def append_message(
    session: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict | None = None,
    platform_message_id: str | None = None,
) -> ConversationMessage | None:
    """Append a message. Returns None if content is empty."""
    if not content or not content.strip():
        return None
    message = ConversationMessage(
        id=str(uuid4()),
        conversation_id=conversation_id,
        role=role,
        content=content.strip(),
        platform_message_id=platform_message_id,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    session.add(message)
    await session.commit()
    return message


async def update_conversation_title(
    session: AsyncSession,
    conversation_id: str,
    title: str,
) -> None:
    """Update conversation title (usually from first user message)."""
    conversation = await session.get(Conversation, conversation_id)
    if conversation:
        conversation.title = title[:500]
        await session.commit()
```

## 3.2 Add fields to `SessionRuntime` in `main.py`

Add two fields to the `SessionRuntime.__init__` method:

```python
class SessionRuntime:
    """In-memory runtime state for a websocket navigation session."""

    def __init__(self) -> None:
        self.task_running = False
        self.current_task: asyncio.Task[None] | None = None
        self.cancel_event = asyncio.Event()
        self.steering_context: list[str] = []
        self.queued_instructions: list[str] = []
        self.settings: dict[str, Any] = {}
        self.conversation_id: str | None = None
        self.user_uid: str | None = None
```

## 3.3 Wire into `websocket_navigate` in `main.py`

Add imports at top of `main.py`:

```python
from backend.conversation_service import get_or_create_conversation, append_message, update_conversation_title
from backend.database import _session_factory
```

In `websocket_navigate`, after `runtime = SessionRuntime()`, add user extraction:

```python
    # Extract user from session cookie for conversation logging
    try:
        cookies = websocket.cookies
        token = cookies.get("aegis_session")
        ws_payload = _verify_session(token)
        if ws_payload:
            runtime.user_uid = ws_payload.get("uid")
    except Exception:  # noqa: BLE001
        pass
```

In the `if action == "navigate":` block, AFTER `_start_navigation_task(...)`, add:

```python
                # Log conversation (fire-and-forget)
                if runtime.user_uid and _session_factory:
                    try:
                        async with _session_factory() as db_sess:
                            conv = await get_or_create_conversation(db_sess, runtime.user_uid, "web", session_id)
                            runtime.conversation_id = conv.id
                            await append_message(db_sess, runtime.conversation_id, "user", instruction)
                            await update_conversation_title(db_sess, runtime.conversation_id, instruction[:200])
                    except Exception:  # noqa: BLE001
                        logger.debug("Conversation logging failed", exc_info=True)
```

In the `elif action == "steer":` block, after the existing `_send_step`, add:

```python
                if runtime.conversation_id and _session_factory:
                    try:
                        async with _session_factory() as db_sess:
                            await append_message(db_sess, runtime.conversation_id, "user", f"[steer] {instruction}")
                    except Exception:  # noqa: BLE001
                        logger.debug("Steer logging failed", exc_info=True)
```

In `_run_navigation_task`, after the final `await websocket.send_json({"type": "result", ...})` success send, add:

```python
        # Log result (fire-and-forget)
        if runtime.conversation_id and _session_factory:
            try:
                async with _session_factory() as db_sess:
                    summary = result.get("status", "completed") if isinstance(result, dict) else "completed"
                    await append_message(db_sess, runtime.conversation_id, "assistant", f"Task {summary}: {instruction}")
            except Exception:  # noqa: BLE001
                logger.debug("Result logging failed", exc_info=True)
```

## 3.4 Wire into integration webhooks in `main.py`

After each integration webhook handler's result, add fire-and-forget conversation logging following the same pattern. For Telegram webhook (after `result = await integration.execute_tool(...)`):

```python
    if _session_factory:
        try:
            async with _session_factory() as db_sess:
                message = update.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                text_content = message.get("text", "")
                if chat_id and text_content:
                    conv = await get_or_create_conversation(db_sess, f"telegram:{chat_id}", "telegram", chat_id)
                    await append_message(db_sess, conv.id, "user", text_content)
        except Exception:  # noqa: BLE001
            logger.debug("Telegram conversation logging failed", exc_info=True)
```

Same pattern for Slack and Discord send-message endpoints.

---

# PHASE 4 — Admin Frontend Panel

## 4.1 Install react-router-dom

Add to `frontend/package.json` dependencies:

```json
"react-router-dom": "^7.4.0"
```

Run `npm install` to update `package-lock.json`.

## 4.2 Extract ClientDashboard from App.tsx

Create `frontend/src/components/ClientDashboard.tsx` — move the entire authenticated main view (everything the current `App.tsx` renders when `isAuthenticated && !showLanding` is true) into this new component. This is a **pure extraction** — no logic changes. The component should use all the same hooks internally (`useWebSocket`, `useUsage`, `useSettingsContext`, `useMicrophone`) and render the full existing UI (sidebar, header, usage bar, URL bar, ScreenView, ActionLog, InputBar, settings modal, etc.).

Props it receives:

```tsx
type ClientDashboardProps = {
  authUser: { uid: string; name: string; email: string; avatar_url?: string | null; role?: string } | null
  onSignOut: () => void
  isAdmin?: boolean
}
```

If `isAdmin` is true, show an "Admin Panel" link in the sidebar:

```tsx
{isAdmin && (
  <a href="/admin" className="flex items-center gap-2 rounded border border-[#2a2a2a] px-2 py-2 text-xs text-zinc-300 hover:bg-zinc-800">
    <LuShield className="h-3.5 w-3.5" />
    Admin Panel
  </a>
)}
```

Import `LuShield` from `react-icons/lu`.

## 4.3 Rewrite App.tsx with routes

```tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { AuthPage } from './components/AuthPage'
import { ClientDashboard } from './components/ClientDashboard'
import { LandingPage } from './components/LandingPage'
import { AdminLayout } from './admin/AdminLayout'
import { ImpersonationBanner } from './admin/components/ImpersonationBanner'
import { apiUrl } from './lib/api'

type AuthUser = {
  uid: string
  name: string
  email: string
  avatar_url?: string | null
  role?: string
  impersonating?: boolean
  admin_uid?: string
}

function App() {
  const navigate = useNavigate()
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [authUser, setAuthUser] = useState<AuthUser | null>(null)
  const [authLoading, setAuthLoading] = useState(true)

  useEffect(() => {
    let active = true
    const loadAuth = async () => {
      try {
        const response = await fetch(apiUrl('/api/auth/me'), { credentials: 'include' })
        if (!response.ok) {
          if (active) { setIsAuthenticated(false); setAuthUser(null) }
          return
        }
        const data = await response.json().catch(() => ({}))
        if (active && data?.user) { setAuthUser(data.user); setIsAuthenticated(true) }
      } finally {
        if (active) setAuthLoading(false)
      }
    }
    void loadAuth()
    return () => { active = false }
  }, [])

  const handleAuth = useCallback((user: AuthUser) => {
    setAuthUser(user)
    setIsAuthenticated(true)
    navigate(user.role === 'admin' || user.role === 'superadmin' ? '/admin' : '/app')
  }, [navigate])

  const handleSignOut = useCallback(async () => {
    await fetch(apiUrl('/api/auth/logout'), { method: 'POST', credentials: 'include' })
    setAuthUser(null)
    setIsAuthenticated(false)
    navigate('/')
  }, [navigate])

  const isAdmin = authUser?.role === 'admin' || authUser?.role === 'superadmin'
  const isImpersonating = authUser?.impersonating === true

  if (authLoading) {
    return (
      <main className='flex h-screen items-center justify-center bg-[#111] text-zinc-100'>
        <div className='rounded-full border border-[#2a2a2a] bg-[#1a1a1a] px-4 py-2 text-sm text-zinc-400'>
          Checking session…
        </div>
      </main>
    )
  }

  return (
    <div className={isImpersonating ? 'pt-10' : ''}>
      {isImpersonating && <ImpersonationBanner email={authUser?.email ?? ''} />}
      <Routes>
        <Route path='/' element={
          !isAuthenticated
            ? <LandingPage onGetStarted={() => navigate('/auth')} />
            : <Navigate to={isAdmin ? '/admin' : '/app'} replace />
        } />
        <Route path='/auth' element={
          !isAuthenticated
            ? <AuthPage onAuthenticated={handleAuth} onBack={() => navigate('/')} />
            : <Navigate to={isAdmin ? '/admin' : '/app'} replace />
        } />
        <Route path='/app/*' element={
          isAuthenticated
            ? <ClientDashboard authUser={authUser} onSignOut={handleSignOut} isAdmin={isAdmin} />
            : <Navigate to='/auth' replace />
        } />
        <Route path='/admin/*' element={
          isAuthenticated && isAdmin
            ? <AdminLayout authUser={authUser} onSignOut={handleSignOut} />
            : <Navigate to={isAuthenticated ? '/app' : '/auth'} replace />
        } />
        <Route path='*' element={<Navigate to='/' replace />} />
      </Routes>
    </div>
  )
}

export default App
```

**IMPORTANT**: Check that `LandingPage` currently receives `onGetStarted` as a prop. If it doesn't, check its actual props interface and match it. Same for `AuthPage`'s `onAuthenticated` and `onBack` — check their actual prop names and match exactly.

## 4.4 Update `frontend/src/main.tsx`

Wrap with `BrowserRouter`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { SettingsProvider } from './context/SettingsContext'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <SettingsProvider>
        <App />
      </SettingsProvider>
    </BrowserRouter>
  </StrictMode>,
)
```

## 4.5 Create `frontend/src/admin/DetailPanelContext.tsx`

```tsx
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

type DetailPanelContextType = {
  content: ReactNode | null
  isOpen: boolean
  openPanel: (content: ReactNode) => void
  closePanel: () => void
}

const DetailPanelContext = createContext<DetailPanelContextType>({
  content: null, isOpen: false, openPanel: () => {}, closePanel: () => {},
})

export function DetailPanelProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<ReactNode | null>(null)
  const isOpen = content !== null

  const openPanel = useCallback((node: ReactNode) => { setContent(node) }, [])
  const closePanel = useCallback(() => { setContent(null) }, [])

  return (
    <DetailPanelContext.Provider value={{ content, isOpen, openPanel, closePanel }}>
      {children}
    </DetailPanelContext.Provider>
  )
}

export function useDetailPanel() {
  return useContext(DetailPanelContext)
}
```

## 4.6 Create `frontend/src/admin/AdminLayout.tsx`

Admin layout with collapsible sidebar + main content area + slide-out detail panel.

```tsx
import { useState } from 'react'
import { NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import {
  LuArrowLeftRight, LuBot, LuCreditCard, LuLayoutDashboard,
  LuMessageSquare, LuPanelLeftClose, LuPanelLeftOpen, LuShield,
  LuSettings, LuUsers, LuX,
} from 'react-icons/lu'
import { DetailPanelProvider, useDetailPanel } from './DetailPanelContext'
import { DashboardPage } from './pages/DashboardPage'
import { UsersPage } from './pages/UsersPage'
import { BillingPage } from './pages/BillingPage'
import { ConversationsPage } from './pages/ConversationsPage'
import { AgentsPage } from './pages/AgentsPage'
import { AuditPage } from './pages/AuditPage'
import { AdminSettingsPage } from './pages/AdminSettingsPage'
```

Structure:
- **Sidebar**: 240px expanded / 56px collapsed. `bg-[#171717] border-r border-[#2a2a2a]`. Toggle via `LuPanelLeftOpen`/`LuPanelLeftClose`.
- **Nav items**: `NavLink` components. Active: `bg-blue-600/20 text-blue-400 rounded-lg`. Inactive: `text-zinc-400 hover:bg-[#222] hover:text-zinc-200 rounded-lg`. Each has an icon + label (label hidden when collapsed).
- **Nav links**: Dashboard (`/admin`, end match), Users (`/admin/users`), Billing (`/admin/billing`), Conversations (`/admin/conversations`), Agents (`/admin/agents`), Audit (`/admin/audit`), Settings (`/admin/settings`). Plus "Switch to App" button at bottom → navigates to `/app`.
- **Main area**: `Routes` rendering the page components.
- **Detail panel overlay**: 480px wide, slides from right. `bg-[#1a1a1a] border-l border-[#2a2a2a]`. Close button with `LuX`. Backdrop: `bg-black/30`, click to close. Content from `useDetailPanel()`.
- Wrap everything in `<DetailPanelProvider>`.

Props:

```tsx
type AdminLayoutProps = {
  authUser: { uid: string; name: string; email: string; avatar_url?: string | null; role?: string } | null
  onSignOut: () => void
}
```

## 4.7 Create admin hooks in `frontend/src/admin/hooks/`

Each hook handles API calls. Pattern:

```tsx
import { useCallback, useState } from 'react'
import { apiUrl } from '../../lib/api'

// Types for the data this hook manages
// useCallback for all fetch/mutate functions
// Return { data, loading, error, fetchFn, mutateFn, ... }
```

Create:
- **`useAdminDashboard.ts`** — `fetchDashboard()` → `GET /api/admin/dashboard/`
- **`useAdminUsers.ts`** — `fetchUsers(params)`, `getUser(uid)`, `updateUser(uid, data)`, `suspendUser(uid)`, `reinstateUser(uid)`, `adjustCredits(uid, amount, reason)`, `changeRole(uid, role)`
- **`useAdminBilling.ts`** — `getPaymentMethods(uid)`, `addPaymentMethod(uid, data)`, `setDefaultPayment(uid, pmId)`, `removePaymentMethod(uid, pmId)`, `changePlan(uid, plan, allowance)`
- **`useAdminConversations.ts`** — `fetchConversations(params)`, `getConversation(id)`, `getUserConversations(uid)`, `getStats()`
- **`useAdminAudit.ts`** — `fetchAudit(params)` with filters
- **`useImpersonation.ts`** — `startImpersonation(target)` → `POST /api/admin/impersonate/start`, `stopImpersonation()` → `POST /api/admin/impersonate/stop`, `checkStatus()` → `GET /api/admin/impersonate/status`

## 4.8 Create shared admin components in `frontend/src/admin/components/`

### `StatsCard.tsx`
- Props: `{ icon: ReactNode, label: string, value: string | number }`
- Card: `bg-[#1a1a1a] border border-[#2a2a2a] rounded-xl p-4`
- Icon top-left, label in `text-zinc-400 text-xs`, value in `text-2xl font-bold text-zinc-100`

### `PlatformBadge.tsx`
- Props: `{ platform: string }`
- Colored pill: web → blue, telegram → sky, slack → purple, discord → indigo, github → zinc

### `RoleBadge.tsx`
- Props: `{ role: string }`
- Colored pill: user → zinc, admin → blue, superadmin → amber

### `StatusBadge.tsx`
- Props: `{ status: string }`
- Colored pill: active → green, suspended → yellow, banned → red

### `ImpersonationBanner.tsx`
- Fixed `top-0 inset-x-0 z-50`. `bg-amber-500/10 border-b border-amber-500/30`.
- `LuTriangleAlert` icon + "You are viewing as **{email}**" + "Exit Impersonation" button
- Exit button: `POST /api/admin/impersonate/stop` then `window.location.href = '/admin/users'`

## 4.9 Create admin pages in `frontend/src/admin/pages/`

### `DashboardPage.tsx`
- Fetch from `useAdminDashboard`
- Grid of `StatsCard` components: Total Users, Active (7d), New This Month, Credits Used, Active Conversations
- Recent activity list from dashboard response
- Platform breakdown with colored bars (no chart library)

### `UsersPage.tsx`
- Search input + role dropdown + status dropdown
- Table: User (avatar initials + name + email), Role (RoleBadge), Status (StatusBadge), Last Login, Actions
- Row click → open `UserDetailPanel` in detail panel context
- Quick actions: `LuEye` (view detail), `LuBan` (suspend), `LuCheck` (reinstate)
- Pagination: Previous/Next with offset tracking

### `UserDetailPanel.tsx`
- Renders in the slide-out detail panel. Receives `uid` prop.
- Header: initials circle, name, email, RoleBadge, StatusBadge
- Tabs: Overview | Billing | Conversations
- **Overview**: info grid, action buttons (suspend/reinstate), role selector (superadmin only via `LuShield`)
- **Billing**: payment methods, plan selector, credit adjustment
- **Conversations**: list user's conversations
- "View as User" button: amber styled, `LuEye` icon, `window.confirm` then `startImpersonation(uid)` then `window.location.href = '/app'`

### `ConversationsPage.tsx`
- Filter: platform dropdown, user search, date
- List of conversation cards: user info, PlatformBadge, title, message count, last activity
- Click → open `ConversationViewer` in detail panel

### `ConversationViewer.tsx`
- In detail panel. Fetches conversation with messages.
- Header: PlatformBadge + user + title + date
- Chat bubbles: user right-aligned (blue bg), assistant left (gray bg), system centered
- Timestamps on messages

### `AuditPage.tsx`
- Filters: admin dropdown, action type, target user, date range
- Table: Timestamp, Admin, Action, Target, Details preview, IP
- Click row → expand full JSON details

### `BillingPage.tsx`
- Overview cards: total paying users, estimated MRR (derive from plan counts)
- Quick user search → links to UserDetailPanel billing tab

### `AgentsPage.tsx`
- Stats from `GET /api/admin/agents/stats` (if the Phase 6 admin agents router exists)
- Table of recent agent tasks from `GET /api/admin/agents/tasks`
- If admin agents endpoints don't exist yet, show a "Coming soon" placeholder

### `AdminSettingsPage.tsx`
- List current admins/superadmins (filter users by role)
- "Add admin by email" input (calls `changeRole`)
- System defaults display

---

# PHASE 5 — Impersonation + Polish

## 5.1 Impersonation flow

Everything should be wired from Phase 4 above:
1. Admin clicks "View as User" in UserDetailPanel → confirms → `POST /api/admin/impersonate/start` → `window.location.href = '/app'`
2. App.tsx checks `authUser.impersonating` → shows `ImpersonationBanner` + adds `pt-10`
3. Banner's "Exit" button → `POST /api/admin/impersonate/stop` → `window.location.href = '/admin/users'`

## 5.2 Loading states

All admin pages: show a centered `LuLoader` with `animate-spin` while loading:

```tsx
{loading && (
  <div className='flex items-center justify-center py-12'>
    <LuLoader className='h-6 w-6 animate-spin text-zinc-500' />
  </div>
)}
```

## 5.3 Empty states

When no data:

```tsx
{!loading && items.length === 0 && (
  <div className='flex flex-col items-center justify-center py-12 text-center'>
    <LuSearch className='mb-2 h-8 w-8 text-zinc-600' />
    <p className='text-sm text-zinc-500'>No results found</p>
  </div>
)}
```

## 5.4 Error states

Catch fetch errors and show inline:

```tsx
{error && (
  <div className='rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300'>
    {error}
  </div>
)}
```

---

## Final file structure

```
backend/admin/
├── __init__.py              (existing — unchanged)
├── audit.py                 (NEW)
├── audit_service.py         (FIX bugs)
├── billing.py               (NEW)
├── conversations.py         (NEW)
├── dashboard.py             (existing — unchanged)
├── dependencies.py          (existing — unchanged)
├── impersonation.py         (NEW)
├── router.py                (UPDATED — mount new sub-routers)
└── users.py                 (NEW)

backend/conversation_service.py    (NEW)

main.py                            (MODIFIED — SessionRuntime fields, conversation imports, logging)

frontend/src/
├── admin/
│   ├── AdminLayout.tsx
│   ├── DetailPanelContext.tsx
│   ├── components/
│   │   ├── ImpersonationBanner.tsx
│   │   ├── PlatformBadge.tsx
│   │   ├── RoleBadge.tsx
│   │   ├── StatsCard.tsx
│   │   └── StatusBadge.tsx
│   ├── hooks/
│   │   ├── useAdminAudit.ts
│   │   ├── useAdminBilling.ts
│   │   ├── useAdminConversations.ts
│   │   ├── useAdminDashboard.ts
│   │   ├── useAdminUsers.ts
│   │   └── useImpersonation.ts
│   └── pages/
│       ├── AdminSettingsPage.tsx
│       ├── AgentsPage.tsx
│       ├── AuditPage.tsx
│       ├── BillingPage.tsx
│       ├── ConversationViewer.tsx
│       ├── ConversationsPage.tsx
│       ├── DashboardPage.tsx
│       ├── UserDetailPanel.tsx
│       └── UsersPage.tsx
├── components/
│   ├── ClientDashboard.tsx  (NEW — extracted from App.tsx)
│   └── ... (all existing files UNCHANGED)
├── App.tsx                  (REWRITTEN — router-based)
├── main.tsx                 (MODIFIED — BrowserRouter wrapper)
└── ... (all other existing files UNCHANGED)
```

---

## Verification checklist

- [ ] `backend/admin/audit_service.py` bugs fixed (no duplicate `session.add`, no unreachable code)
- [ ] All 6 admin sub-routers mount correctly in `router.py`
- [ ] Admin endpoints return 403 for non-admin users
- [ ] Impersonation start/stop/status endpoints work
- [ ] `backend/conversation_service.py` exists with get_or_create, append, update_title
- [ ] WebSocket handler logs conversations without breaking existing flow
- [ ] `cd frontend && npm install` succeeds (react-router-dom installed)
- [ ] `cd frontend && npm run build` — zero errors
- [ ] `cd frontend && npm run lint` — zero errors
- [ ] Landing page at `/` still works
- [ ] Auth at `/auth` still works
- [ ] Client dashboard at `/app` has ALL existing functionality
- [ ] Admin panel at `/admin` renders with sidebar + dashboard
- [ ] All admin pages render (users, billing, conversations, agents, audit, settings)
- [ ] Detail panel slides open/close
- [ ] Impersonation flow works end-to-end
- [ ] ImpersonationBanner renders and "Exit" works
- [ ] No emojis anywhere — only `react-icons`
- [ ] App starts without import errors (`python -c "from backend.admin import admin_router"`)
