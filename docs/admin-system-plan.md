# Aegis Admin System — Architecture Plan

## Current State Analysis

### What exists
- **Auth**: HMAC-signed session cookie (`aegis_session`), no role field on User model
- **User model**: `uid`, `provider`, `email`, `name`, `avatar_url`, `password_hash`, timestamps — no `role`, no `status`
- **Frontend routing**: No router library — App.tsx uses state flags (`isAuthenticated`, `showLanding`, `showSettings`) to switch views
- **Conversations**: Ephemeral only — WebSocket sessions in-memory, no persistence
- **Integrations**: In-memory registries (Telegram, Slack, Discord) — no conversation logging
- **Billing**: CreditBalance + UsageEvent + CreditTopUp models exist, but no payment method storage (no Stripe)

### What needs to be built
1. Role-based access control (RBAC) on both backend and frontend
2. Admin panel with dual-slider layout
3. User management CRUD with search/filter/bulk actions
4. Billing management with payment method control
5. Cross-platform conversation access (persistent storage)
6. User impersonation system with audit trail
7. Agent/session monitoring
8. Audit logging for all admin actions

---

## 1. Database Schema Changes

### 1a. Modify `User` model
```python
class User(Base):
    __tablename__ = "users"
    uid = Column(String(255), primary_key=True)
    provider = Column(String(50))
    provider_id = Column(String(255))
    email = Column(String(320))
    name = Column(String(255))
    avatar_url = Column(Text)
    password_hash = Column(Text)
    role = Column(String(20), default="user")         # NEW: "user" | "admin" | "superadmin"
    status = Column(String(20), default="active")      # NEW: "active" | "suspended" | "banned"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), onupdate=func.now())
```

### 1b. New models

```python
class Conversation(Base):
    """Persistent conversation record across all platforms."""
    __tablename__ = "conversations"
    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    platform = Column(String(50), nullable=False)   # "web" | "telegram" | "slack" | "discord"
    platform_chat_id = Column(String(255))           # external chat/channel ID
    title = Column(String(500))                       # auto-generated from first message
    status = Column(String(20), default="active")     # "active" | "archived"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class ConversationMessage(Base):
    """Individual message within a conversation."""
    __tablename__ = "conversation_messages"
    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    conversation_id = Column(String(255), ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)        # "user" | "assistant" | "system"
    content = Column(Text, nullable=False)
    platform_message_id = Column(String(255))
    metadata_json = Column(Text)                      # JSON: tokens used, model, provider, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PaymentMethod(Base):
    """Stored payment method for a user (Stripe-backed)."""
    __tablename__ = "payment_methods"
    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    stripe_customer_id = Column(String(255))
    stripe_payment_method_id = Column(String(255))
    type = Column(String(30))                         # "card" | "bank" | "paypal"
    brand = Column(String(30))                        # "visa" | "mastercard" etc.
    last4 = Column(String(4))
    exp_month = Column(Integer)
    exp_year = Column(Integer)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    """Immutable log of all admin actions."""
    __tablename__ = "audit_logs"
    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    admin_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    action = Column(String(100), nullable=False)       # "user.suspend", "billing.update_plan", "impersonate.start", etc.
    target_user_id = Column(String(255), index=True)
    details_json = Column(Text)                        # JSON blob with action-specific data
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

class ImpersonationSession(Base):
    """Track when admins are impersonating user accounts."""
    __tablename__ = "impersonation_sessions"
    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    admin_id = Column(String(255), ForeignKey("users.uid"), nullable=False)
    target_user_id = Column(String(255), ForeignKey("users.uid"), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text)
```

### 1c. Schema migration strategy
- Use `_ensure_user_columns_sync` pattern (already exists) for `role` and `status` columns on `users`
- All new tables created via `Base.metadata.create_all` (already called at startup)
- No external migration tool needed at this stage

---

## 2. Backend Admin Module

### File structure
```
backend/admin/
├── __init__.py          # Export router
├── dependencies.py      # require_admin(), require_superadmin(), get_admin_user()
├── router.py            # Main admin API router (mounts sub-routers)
├── users.py             # User CRUD endpoints
├── billing.py           # Billing/payment management endpoints
├── conversations.py     # Cross-platform conversation access
├── impersonation.py     # User impersonation start/stop
├── agents.py            # Agent/session monitoring
├── audit.py             # Audit log endpoints
└── dashboard.py         # Overview stats endpoint
```

### 2a. Admin dependencies (`dependencies.py`)
```python
async def get_admin_user(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    """Extract user from session, verify role is admin or superadmin."""
    user = _get_current_user(request)  # reuse existing helper
    db_user = await session.get(User, user["uid"])
    if not db_user or db_user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    if db_user.status != "active":
        raise HTTPException(status_code=403, detail="Account suspended")
    return {**user, "role": db_user.role}

async def require_superadmin(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    """Only superadmins can manage other admins."""
    admin = await get_admin_user(request, session)
    if admin["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return admin
```

### 2b. Admin API endpoints

**Dashboard** (`GET /api/admin/dashboard`)
- Total users, active users (last 7d), new signups (this month)
- Total revenue, MRR estimate
- Active sessions count
- Credit usage aggregates
- Top models by usage

**Users** (`/api/admin/users`)
- `GET /api/admin/users` — paginated list with search (email, name), filter (role, status, plan), sort
- `GET /api/admin/users/{uid}` — full user detail (profile + balance + usage + conversations + payment methods)
- `PUT /api/admin/users/{uid}` — update role, status, name, email
- `PUT /api/admin/users/{uid}/plan` — change plan, adjust monthly allowance
- `POST /api/admin/users/{uid}/suspend` — suspend account
- `POST /api/admin/users/{uid}/reinstate` — reactivate account
- `DELETE /api/admin/users/{uid}` — soft-delete (set status=banned)
- `POST /api/admin/users/{uid}/credit-adjustment` — add/remove credits manually

**Billing** (`/api/admin/billing`)
- `GET /api/admin/billing/users/{uid}/payment-methods` — list payment methods
- `POST /api/admin/billing/users/{uid}/payment-methods` — add payment method (admin override)
- `PUT /api/admin/billing/users/{uid}/payment-methods/{id}/default` — set default
- `DELETE /api/admin/billing/users/{uid}/payment-methods/{id}` — remove
- `POST /api/admin/billing/users/{uid}/charge` — manual charge
- `GET /api/admin/billing/revenue` — revenue dashboard data

**Conversations** (`/api/admin/conversations`)
- `GET /api/admin/conversations` — list all conversations (filterable by user, platform, date)
- `GET /api/admin/conversations/{id}` — full conversation with messages
- `GET /api/admin/conversations/user/{uid}` — all conversations for a user
- `GET /api/admin/conversations/platforms` — per-platform stats

**Impersonation** (`/api/admin/impersonate`)
- `POST /api/admin/impersonate/start` — body: `{ target_email_or_uid }` → returns impersonation session cookie
- `POST /api/admin/impersonate/stop` — ends impersonation, restores admin session
- `GET /api/admin/impersonate/active` — check if currently impersonating

**Agents** (`/api/admin/agents`)
- `GET /api/admin/agents/sessions` — active WebSocket sessions
- `GET /api/admin/agents/config` — global agent configuration
- `PUT /api/admin/agents/config` — update defaults (default model, system instructions, etc.)

**Audit** (`/api/admin/audit`)
- `GET /api/admin/audit` — paginated audit log with filter by admin, action type, target user, date range

### 2c. Impersonation mechanism
- When admin starts impersonation:
  1. Store current admin session in a separate cookie (`aegis_admin_session`)
  2. Issue a new `aegis_session` cookie as if the target user logged in
  3. Add `impersonating: true` and `admin_uid` to session payload
  4. Record in `ImpersonationSession` table + audit log
- When admin stops:
  1. Restore `aegis_session` from `aegis_admin_session`
  2. Delete `aegis_admin_session`
  3. Update `ended_at` on impersonation record
- Frontend shows a persistent banner: "You are viewing as [user email] — Exit impersonation"
- All actions during impersonation are logged with `impersonated_by: admin_uid`

### 2d. Conversation persistence
- Modify WebSocket handler in `main.py`:
  - On "navigate" action: create or continue a `Conversation` (platform="web")
  - On each step/result: append `ConversationMessage`
- Modify integration webhook handlers:
  - `telegram_webhook`: log incoming and outgoing messages
  - `slack_send_message`: log messages
  - `discord_send_message`: log messages
- Each platform handler creates conversations lazily (first message creates it)

---

## 3. Auth System Changes

### 3a. Session payload update
Add to `_sign_session` payload:
```python
{
    "uid": ...,
    "email": ...,
    "name": ...,
    "role": "user" | "admin" | "superadmin",   # NEW
    "impersonating": False,                      # NEW
    "admin_uid": None,                           # NEW (set during impersonation)
}
```

### 3b. `_upsert_user` changes
- Include `role` in returned payload (default "user" for new users)
- Include `status` check — reject login if status != "active"

### 3c. Login redirect logic
- `/api/auth/me` response now includes `role`
- Frontend checks `role` on auth check and routes accordingly

### 3d. Admin seed
- Add config: `ADMIN_EMAILS` env var (comma-separated)
- On first login, if email matches `ADMIN_EMAILS`, auto-assign role="admin"
- Or: CLI/API endpoint for superadmin to promote users

---

## 4. Frontend Architecture

### 4a. Install React Router
```bash
npm install react-router-dom
```

### 4b. Route structure
```
/                    → LandingPage (unauthenticated)
/auth                → AuthPage (signin/signup)
/app                 → Client dashboard (current main view)
/app/settings        → Client settings
/admin               → Admin dashboard (redirects to /auth if not admin)
/admin/users         → User management
/admin/users/:uid    → User detail
/admin/billing       → Billing overview
/admin/conversations → Conversation browser
/admin/agents        → Agent monitoring
/admin/audit         → Audit log
/admin/settings      → Admin settings / global config
```

### 4c. Admin Layout Component (`AdminLayout.tsx`)

**Left sidebar (collapsible):**
```
┌──────────────────┐
│  AEGIS ADMIN     │  ← Logo + collapse toggle
│                  │
│  ▸ Dashboard     │  ← Overview stats
│  ▸ Users         │  ← User management table
│  ▸ Billing       │  ← Revenue + payment methods
│  ▸ Conversations │  ← Cross-platform viewer
│  ▸ Agents        │  ← Active sessions/config
│  ▸ Audit Log     │  ← Admin action history
│  ▸ Settings      │  ← Global config
│                  │
│  ────────────    │
│  ▸ Switch to App │  ← Go to client view
│  Admin Name      │  ← Profile/logout
└──────────────────┘
```

**Main area with slide-out detail panels:**
- Main content takes full width when no detail panel is open
- Clicking a user row slides in a detail panel from the right (independent scroll)
- Detail panel has its own tabs (profile, billing, conversations, usage)
- Both sidebar and detail panel can be independently opened/closed
- This is the "both sliders on both the side navbar and main screen" Jesse described

### 4d. Key admin components

```
frontend/src/admin/
├── AdminLayout.tsx           # Sidebar + main + detail panel shell
├── AdminSidebar.tsx          # Collapsible nav sidebar
├── AdminDetailPanel.tsx      # Slide-out right panel wrapper
├── AdminRoute.tsx            # Protected route (checks role)
├── pages/
│   ├── DashboardPage.tsx     # Stats cards, charts, recent activity
│   ├── UsersPage.tsx         # Searchable table + bulk actions
│   ├── UserDetailPanel.tsx   # Right-panel: user profile, billing, conversations
│   ├── BillingPage.tsx       # Revenue overview, payment method management
│   ├── ConversationsPage.tsx # Platform filter + conversation list
│   ├── ConversationViewer.tsx# Full message thread viewer
│   ├── AgentsPage.tsx        # Active sessions, global config
│   ├── AuditPage.tsx         # Filterable audit log table
│   └── AdminSettingsPage.tsx # Global admin settings
├── components/
│   ├── UserTable.tsx         # Sortable/filterable user table
│   ├── UserRow.tsx           # Individual row with quick actions
│   ├── BillingCard.tsx       # Payment method display card
│   ├── PlanSelector.tsx      # Dropdown to change user plan
│   ├── CreditAdjuster.tsx    # Input to add/remove credits
│   ├── ConversationList.tsx  # Filterable conversation list
│   ├── MessageThread.tsx     # Chat-style message display
│   ├── PlatformBadge.tsx     # web/telegram/slack/discord badge
│   ├── ImpersonationBanner.tsx # "Viewing as user — Exit" banner
│   ├── StatsCard.tsx         # Dashboard metric card
│   └── AdminSearchBar.tsx    # Global search (users, conversations)
└── hooks/
    ├── useAdminUsers.ts      # Fetch/search/filter users
    ├── useAdminBilling.ts    # Billing data
    ├── useAdminConversations.ts
    ├── useAdminAudit.ts
    ├── useAdminDashboard.ts
    └── useImpersonation.ts   # Start/stop/check impersonation
```

### 4e. Impersonation flow (frontend)
1. Admin clicks "View as user" on user detail panel
2. Confirm modal: "You will switch to [user]'s account. All actions will be logged."
3. `POST /api/admin/impersonate/start` with user's email/uid
4. Page reloads — `GET /api/auth/me` now returns the target user with `impersonating: true`
5. App detects `impersonating: true` → shows `ImpersonationBanner` at top of every page
6. Banner has "Exit" button → `POST /api/admin/impersonate/stop` → reload → back to admin panel
7. While impersonating, admin sees exactly what the user sees (including their settings, conversations, integrations)

### 4f. Auto-redirect on login
Current `AuthPage` calls `onAuthenticated(user)` on success. Update to:
```typescript
// In App.tsx or router
if (user.role === 'admin' || user.role === 'superadmin') {
  navigate('/admin')
} else {
  navigate('/app')
}
```
Admins can still access `/app` (the client view) via "Switch to App" in sidebar.

---

## 5. Conversation Storage Integration

### 5a. WebSocket session logging
In `main.py` `websocket_navigate` handler:
```python
# On first "navigate" action:
conversation = await create_conversation(session, user_uid, "web", session_id)
# On each message/step:
await append_message(session, conversation.id, role, content, metadata)
```

### 5b. Platform integration logging
Each integration webhook already processes messages. Add persistence:
- `telegram_webhook`: after processing update, log user message + bot response
- `slack_send_message`: log the sent message
- `discord_send_message`: log the sent message

### 5c. Conversation service (`backend/conversation_service.py`)
```python
async def create_conversation(session, user_id, platform, platform_chat_id=None, title=None)
async def append_message(session, conversation_id, role, content, metadata=None, platform_message_id=None)
async def get_conversations(session, user_id=None, platform=None, limit=50, offset=0)
async def get_conversation_messages(session, conversation_id, limit=100, offset=0)
async def search_conversations(session, query, user_id=None, platform=None)
```

---

## 6. Security Considerations

1. **All admin endpoints behind `get_admin_user` dependency** — role check on every request
2. **Audit logging** — every admin action recorded with IP, timestamp, details
3. **Impersonation** — logged start/stop, visible banner, cannot impersonate superadmin
4. **Rate limiting** — admin endpoints should have rate limits (use `slowapi` or custom)
5. **ADMIN_EMAILS** — env var to auto-assign admin role on first login; no public endpoint to self-promote
6. **Superadmin lock** — only superadmins can promote/demote admins
7. **Session separation** — impersonation uses separate cookie; admin session preserved

---

## 7. Environment Variables (New)

```env
# Admin
ADMIN_EMAILS=jesse@chronos.so                    # auto-admin on first login
ADMIN_SESSION_TTL_SECONDS=3600                    # shorter TTL for admin sessions

# Stripe (future)
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PUBLISHABLE_KEY=pk_...

# Conversation storage
CONVERSATION_RETENTION_DAYS=90                    # auto-cleanup old conversations
```

---

## 8. Implementation Order (for Codex)

**Phase 1 — Foundation** (must be done first):
1. Add `role` + `status` columns to User model + migration helper
2. Update auth to include role in session, add admin seed via ADMIN_EMAILS
3. Create `backend/admin/dependencies.py` with role-check helpers
4. Create `backend/admin/router.py` as mount point

**Phase 2 — Admin API**:
5. Dashboard endpoint
6. User management CRUD endpoints
7. Audit log model + service + endpoints
8. Impersonation backend (start/stop/check)

**Phase 3 — Conversation persistence**:
9. Conversation + ConversationMessage models
10. Conversation service
11. Wire into WebSocket handler
12. Wire into integration webhooks
13. Admin conversation access endpoints

**Phase 4 — Billing**:
14. PaymentMethod model
15. Billing admin endpoints (CRUD payment methods, manual adjustments)

**Phase 5 — Frontend admin panel**:
16. Install react-router-dom, refactor App.tsx to use router
17. AdminLayout with collapsible sidebar
18. AdminRoute guard component
19. DashboardPage
20. UsersPage + UserDetailPanel (slide-out)
21. ConversationsPage + ConversationViewer
22. BillingPage
23. AuditPage
24. ImpersonationBanner + flow
25. Auto-redirect on login (admin → /admin, user → /app)

**Phase 6 — Polish**:
26. Admin search
27. Bulk actions on user table
28. Export functionality (CSV)
29. Mobile-responsive admin layout
