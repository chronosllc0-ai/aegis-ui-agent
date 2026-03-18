# Codex Phase 2: Admin API Endpoints

## Project Context
Aegis is a FastAPI + React/TypeScript app. Backend at repo root. Database: SQLAlchemy async (PostgreSQL/SQLite). Auth: HMAC-signed session cookies. Phase 1 already added `role`/`status` to User, new models (Conversation, ConversationMessage, PaymentMethod, AuditLog, ImpersonationSession), admin dependencies (`backend/admin/dependencies.py`), audit service, and an empty admin router.

## What to implement
Create the full backend admin API: dashboard stats, user management CRUD, billing management, conversation access, impersonation start/stop, and audit log viewing. All endpoints go under `backend/admin/` and mount on the existing router.

## CRITICAL RULES
- All admin endpoints must use `Depends(get_admin_user)` for auth — never expose admin data to regular users
- Superadmin-only operations (role changes, admin promotion) use `Depends(require_superadmin)`
- Every state-changing action must call `log_admin_action()` from `backend/admin/audit_service.py`
- Do NOT modify: `orchestrator.py`, `session.py`, `navigator.py`, `analyzer.py`, `executor.py`, any file in `frontend/`, `backend/providers/*`, `backend/credit_rates.py`, `backend/credit_service.py`
- Use `request.client.host if request.client else None` for IP in audit logs

## Database models available (from Phase 1)
- `User` (uid, provider, email, name, avatar_url, role, status, created_at, last_login_at, password_hash)
- `CreditBalance` (id, user_id, plan, monthly_allowance, credits_used, overage_credits, cycle_start, cycle_end, spending_cap)
- `UsageEvent` (id, user_id, session_id, provider, model, input_tokens, output_tokens, credits_used, credits_charged, raw_cost_usd, created_at)
- `Conversation` (id, user_id, platform, platform_chat_id, title, status, created_at, updated_at)
- `ConversationMessage` (id, conversation_id, role, content, platform_message_id, metadata_json, created_at)
- `PaymentMethod` (id, user_id, stripe_customer_id, type, brand, last4, exp_month, exp_year, is_default, created_at)
- `AuditLog` (id, admin_id, action, target_user_id, details_json, ip_address, created_at)
- `ImpersonationSession` (id, admin_id, target_user_id, started_at, ended_at, reason)

## Dependencies available
```python
from backend.admin.dependencies import get_admin_user, require_superadmin
from backend.admin.audit_service import log_admin_action
from backend.database import (
    User, CreditBalance, UsageEvent, Conversation, ConversationMessage,
    PaymentMethod, AuditLog, ImpersonationSession, get_session,
)
```

---

## 1. Create `backend/admin/dashboard.py`

```python
"""Admin dashboard statistics."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.dependencies import get_admin_user
from backend.database import (
    AuditLog, Conversation, CreditBalance, UsageEvent, User, get_session,
)

router = APIRouter()


@router.get("/")
async def dashboard_stats(
    admin: dict = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return overview statistics for the admin dashboard."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_users = (await session.execute(select(func.count(User.uid)))).scalar() or 0
    active_users = (await session.execute(
        select(func.count(User.uid)).where(User.last_login_at >= week_ago)
    )).scalar() or 0
    new_users_month = (await session.execute(
        select(func.count(User.uid)).where(User.created_at >= month_start)
    )).scalar() or 0
    credits_used_month = (await session.execute(
        select(func.coalesce(func.sum(UsageEvent.credits_charged), 0)).where(
            UsageEvent.created_at >= month_start
        )
    )).scalar() or 0
    active_conversations = (await session.execute(
        select(func.count(Conversation.id)).where(Conversation.status == "active")
    )).scalar() or 0

    # Platform breakdown
    platform_rows = (await session.execute(
        select(Conversation.platform, func.count(Conversation.id)).group_by(Conversation.platform)
    )).all()
    platform_breakdown = {row[0]: row[1] for row in platform_rows}

    # Recent audit entries
    recent_audit_rows = (await session.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(10)
    )).scalars().all()
    recent_activity = [
        {
            "id": entry.id,
            "admin_id": entry.admin_id,
            "action": entry.action,
            "target_user_id": entry.target_user_id,
            "details": json.loads(entry.details_json) if entry.details_json else None,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        for entry in recent_audit_rows
    ]

    return {
        "total_users": total_users,
        "active_users": active_users,
        "new_users_this_month": new_users_month,
        "credits_used_this_month": credits_used_month,
        "active_conversations": active_conversations,
        "platform_breakdown": platform_breakdown,
        "recent_activity": recent_activity,
    }
```

## 2. Create `backend/admin/users.py`

Endpoints:

**`GET /`** — List users with search, filter, sort, pagination
- Query params: `search` (str, match email or name), `role` (str), `status` (str), `sort_by` (str, default "created_at"), `sort_dir` (str, "asc"|"desc"), `limit` (int, default 50), `offset` (int, default 0)
- Returns: `{ users: [...], total: int, limit: int, offset: int }`
- Each user object includes: uid, email, name, role, status, avatar_url, created_at, last_login_at

**`GET /{uid}`** — Full user detail
- Returns: user object + credit_balance (from CreditBalance) + conversation_count + usage_summary (total credits, top models)
- If user not found: 404

**`PUT /{uid}`** — Update user fields
- Body: `{ name?, email?, role?, status? }`
- Role changes require `Depends(require_superadmin)` — create a separate endpoint `PUT /{uid}/role` with superadmin dependency, or check role in the handler
- Log audit action: `"user.update"` with before/after values

**`POST /{uid}/suspend`** — Set status to "suspended"
- Log audit: `"user.suspend"`
- Return updated user

**`POST /{uid}/reinstate`** — Set status to "active"
- Log audit: `"user.reinstate"`
- Return updated user

**`POST /{uid}/credit-adjustment`** — Add or remove credits
- Body: `{ amount: int, reason: str }`
- Positive amount = add credits. Negative = remove.
- Adjust `CreditBalance.credits_used` accordingly (decrease credits_used to add credits)
- Log audit: `"billing.credit_adjustment"` with amount and reason

Use `get_admin_user` dependency on all endpoints. Use `require_superadmin` for role changes only.

## 3. Create `backend/admin/billing.py`

Endpoints:

**`GET /users/{uid}/payment-methods`** — List payment methods for a user
- Returns: list of payment method objects

**`POST /users/{uid}/payment-methods`** — Add a payment method
- Body: `{ type, brand, last4, exp_month, exp_year }`
- No actual Stripe integration — just store the record
- Log audit: `"billing.add_payment_method"`

**`PUT /users/{uid}/payment-methods/{pm_id}/default`** — Set as default
- Unset all other is_default for this user, set this one
- Log audit: `"billing.set_default_payment"`

**`DELETE /users/{uid}/payment-methods/{pm_id}`** — Remove
- Log audit: `"billing.remove_payment_method"`

**`PUT /users/{uid}/plan`** — Change plan
- Body: `{ plan: str, monthly_allowance: int }`
- Update CreditBalance record
- Log audit: `"billing.change_plan"` with old and new plan

## 4. Create `backend/admin/conversations.py`

Endpoints:

**`GET /`** — List conversations with filters
- Query params: `user_id`, `platform`, `status`, `search` (title), `limit` (default 50), `offset` (default 0)
- Returns: `{ conversations: [...], total: int }`
- Each conversation includes: id, user_id, platform, title, status, message_count, created_at, updated_at

**`GET /{conversation_id}`** — Full conversation with messages
- Query params: `limit` (default 100), `offset` (default 0)
- Returns: conversation object + messages array
- Messages: id, role, content, created_at, metadata (parsed from metadata_json)

**`GET /user/{uid}`** — All conversations for a specific user
- Returns: list of conversations
- Same format as list endpoint but filtered by user

**`GET /stats`** — Platform statistics
- Returns: per-platform counts (conversations, messages, unique users)

## 5. Create `backend/admin/impersonation.py`

Endpoints:

**`POST /start`** — Start impersonation session
- Body: `{ target: str }` — email or uid
- Look up user by email first, then by uid
- Cannot impersonate superadmins (return 403)
- Cannot impersonate yourself (return 400)
- Create `ImpersonationSession` record
- Set `aegis_admin_session` cookie = current session cookie value (preserve admin session)
- Issue new `aegis_session` cookie as target user with extra fields: `"impersonating": true, "admin_uid": admin_uid`
- Use the same `_sign_session` from `auth.py` — import it
- Log audit: `"impersonate.start"` with target user
- Return: `{ ok: true, target_user: { uid, email, name } }`

**`POST /stop`** — Stop impersonation
- Read `aegis_admin_session` cookie
- Restore it as `aegis_session`
- Delete `aegis_admin_session` cookie
- Update `ImpersonationSession.ended_at`
- Log audit: `"impersonate.stop"`
- Return: `{ ok: true }`

**`GET /status`** — Check impersonation state
- Check current session payload for `impersonating` flag
- Return: `{ impersonating: bool, target_user?: {...}, admin_uid?: str }`

Import `_sign_session` and `_verify_session` from `auth`:
```python
from auth import _sign_session, _verify_session
```

For cookie setting, return a `JSONResponse` and call `response.set_cookie(...)` using the same parameters as in `auth.py`'s `_session_response`.

## 6. Create `backend/admin/audit.py`

Endpoints:

**`GET /`** — Paginated audit log
- Query params: `admin_id`, `action`, `target_user_id`, `date_from` (ISO string), `date_to` (ISO string), `limit` (default 50), `offset` (default 0)
- Returns: `{ entries: [...], total: int }`
- Each entry: id, admin_id, action, target_user_id, details (parsed JSON), ip_address, created_at

## 7. Update `backend/admin/router.py`

Mount all sub-routers:

```python
"""Admin API router — mounts all admin sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from . import audit, billing, conversations, dashboard, impersonation, users

router = APIRouter(prefix="/api/admin", tags=["admin"])
router.include_router(dashboard.router, prefix="/dashboard")
router.include_router(users.router, prefix="/users")
router.include_router(billing.router, prefix="/billing")
router.include_router(conversations.router, prefix="/conversations")
router.include_router(impersonation.router, prefix="/impersonate")
router.include_router(audit.router, prefix="/audit")
```

---

## Verification
1. All existing tests pass: `pytest tests/ -v`
2. App starts without import errors
3. `GET /api/admin/dashboard` returns 403 for non-admin users
4. `GET /api/admin/dashboard` returns stats for admin users
5. All CRUD operations work when tested with an admin session
