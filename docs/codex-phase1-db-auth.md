# Codex Phase 1: Database Schema + Auth Foundation

## Project Context
Aegis is a FastAPI + React/TypeScript app. Backend is at repo root (`main.py`, `auth.py`, `config.py`, `backend/`). Frontend is at `frontend/` (Vite + React + TypeScript + Tailwind v4). Database uses SQLAlchemy async with PostgreSQL (asyncpg) / SQLite fallback. Auth uses HMAC-signed session cookies (`aegis_session`).

## What to implement
Add role-based access control to the User model, create 5 new database models for the admin system, update auth to include role in session payloads, and add admin seed from environment variable.

## CRITICAL RULES
- Do NOT modify or break any existing functionality
- Do NOT touch: `orchestrator.py`, `session.py`, `navigator.py`, `analyzer.py`, `executor.py`, `mcp_client.py`, any file in `backend/providers/`, `backend/credit_rates.py`, `backend/credit_service.py`, `backend/key_management.py`, any file in `frontend/`
- All existing API endpoints, WebSocket behavior, and auth flows must continue working

---

## 1. Modify `backend/database.py`

### 1a. Add `Boolean` and `ForeignKey` to imports

Current import line:
```python
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func, inspect, text
```

Change to:
```python
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func, inspect, text
```

### 1b. Add `role` and `status` columns to `User` model

Add these two columns to the `User` class, after `password_hash`:
```python
    role = Column(String(20), default="user")       # "user" | "admin" | "superadmin"
    status = Column(String(20), default="active")    # "active" | "suspended" | "banned"
```

### 1c. Add 5 new models (after `CreditTopUp`)

```python
class Conversation(Base):
    """Persistent conversation record across all platforms."""

    __tablename__ = "conversations"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    platform = Column(String(50), nullable=False)
    platform_chat_id = Column(String(255))
    title = Column(String(500))
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ConversationMessage(Base):
    """Individual message within a conversation."""

    __tablename__ = "conversation_messages"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    conversation_id = Column(String(255), ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    platform_message_id = Column(String(255))
    metadata_json = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PaymentMethod(Base):
    """Stored payment method for a user."""

    __tablename__ = "payment_methods"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    stripe_customer_id = Column(String(255))
    stripe_payment_method_id = Column(String(255))
    type = Column(String(30))
    brand = Column(String(30))
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
    action = Column(String(100), nullable=False)
    target_user_id = Column(String(255), index=True)
    details_json = Column(Text)
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class ImpersonationSession(Base):
    """Track when admins impersonate user accounts."""

    __tablename__ = "impersonation_sessions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    admin_id = Column(String(255), ForeignKey("users.uid"), nullable=False)
    target_user_id = Column(String(255), ForeignKey("users.uid"), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text)
```

### 1d. Update `_ensure_user_columns_sync` to add `role` and `status`

Replace the current function:
```python
def _ensure_user_columns_sync(sync_conn) -> None:
    """Apply lightweight schema fixes for local dev without a migration tool."""
    inspector = inspect(sync_conn)
    if "users" not in inspector.get_table_names():
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "password_hash" not in user_columns:
        sync_conn.execute(text("ALTER TABLE users ADD COLUMN password_hash TEXT"))
    if "role" not in user_columns:
        sync_conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user'"))
    if "status" not in user_columns:
        sync_conn.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
```

---

## 2. Modify `config.py`

Add these two fields to the `Settings` class, in the Auth / Sessions section (after `CORS_ORIGINS`):

```python
    ADMIN_EMAILS: str = ""   # comma-separated emails that auto-get admin role on first login
```

---

## 3. Modify `auth.py`

### 3a. Update `_upsert_user` to include `role` and `status`

The function creates or updates a User and returns a dict. Make these changes:

**For existing users** — add `role` and `status` to the returned payload dict:
```python
        payload = {
            "uid": existing.uid,
            "provider": existing.provider,
            "provider_id": existing.provider_id,
            "email": existing.email,
            "name": existing.name,
            "avatar_url": existing.avatar_url,
            "created_at": existing.created_at,
            "last_login_at": now,
            "role": existing.role or "user",
            "status": existing.status or "active",
        }
```

Also, BEFORE returning for existing users, check status:
```python
        if existing.status and existing.status != "active":
            raise HTTPException(status_code=403, detail="Account suspended")
```

**For new users** — check if email matches `ADMIN_EMAILS` and set role:
```python
        # Determine role: auto-admin from ADMIN_EMAILS env var
        admin_emails = [e.strip().lower() for e in settings.ADMIN_EMAILS.split(",") if e.strip()]
        auto_role = "admin" if profile.get("email", "").lower() in admin_emails else "user"

        user = User(
            uid=profile["uid"],
            provider=profile.get("provider"),
            provider_id=profile.get("provider_id"),
            email=profile.get("email"),
            name=profile.get("name"),
            avatar_url=profile.get("avatar_url"),
            password_hash=profile.get("password_hash"),
            role=auto_role,
            status="active",
            created_at=now,
            last_login_at=now,
        )
        session.add(user)
        payload = {
            "uid": user.uid,
            "provider": user.provider,
            "provider_id": user.provider_id,
            "email": user.email,
            "name": user.name,
            "avatar_url": user.avatar_url,
            "created_at": now,
            "last_login_at": now,
            "role": user.role,
            "status": user.status,
        }
```

### 3b. Update `password_login` to include role and status

In the `password_login` endpoint, the returned `user` dict needs `role` and `status`:
```python
    user = {
        "uid": existing.uid,
        "provider": existing.provider,
        "provider_id": existing.provider_id,
        "email": existing.email,
        "name": existing.name,
        "avatar_url": existing.avatar_url,
        "created_at": existing.created_at,
        "last_login_at": existing.last_login_at,
        "role": existing.role or "user",
        "status": existing.status or "active",
    }
```

Also add a status check before the password verify:
```python
    if existing.status and existing.status != "active":
        raise HTTPException(status_code=403, detail="Account suspended")
```

---

## 4. Create `backend/admin/__init__.py`

```python
from .router import router as admin_router

__all__ = ["admin_router"]
```

## 5. Create `backend/admin/dependencies.py`

```python
"""Admin role-check dependencies for FastAPI."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import User, get_session


async def get_admin_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Extract authenticated user and verify admin or superadmin role."""
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db_user = await session.get(User, payload["uid"])
    if not db_user or db_user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    if db_user.status != "active":
        raise HTTPException(status_code=403, detail="Account suspended")
    return {**payload, "role": db_user.role}


async def require_superadmin(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Only superadmins can promote/demote other admins."""
    admin = await get_admin_user(request, session)
    if admin["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return admin
```

## 6. Create `backend/admin/audit_service.py`

```python
"""Audit logging helper for admin actions."""

from __future__ import annotations

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
    """Record an admin action in the audit log."""
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

## 7. Create `backend/admin/router.py` (placeholder — endpoints added in Phase 2)

```python
"""Admin API router — mounts all admin sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/admin", tags=["admin"])
```

## 8. Mount admin router in `main.py`

Add this import near the top, after the existing auth import:
```python
from backend.admin import admin_router
```

Add this line after `app.include_router(auth_router)`:
```python
app.include_router(admin_router)
```

---

## Verification
1. `python -c "from backend.database import *; print('OK')"` — imports work
2. `python -c "from backend.admin import admin_router; print('OK')"` — admin module imports
3. `python -c "from auth import router; print('OK')"` — auth still imports
4. All existing tests pass: `pytest tests/ -v`
5. The app starts: `uvicorn main:app --host 0.0.0.0 --port 8000` (no import errors)
