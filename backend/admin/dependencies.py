"""FastAPI dependencies for admin-only routes."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

import auth
from backend.database import User, get_session


async def get_admin_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Return the authenticated admin user after validating session and account state."""
    token = request.cookies.get("aegis_session")
    payload = auth._verify_session(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")

    uid = payload.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await session.get(User, uid)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account suspended")
    if user.role not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_superadmin(
    admin_user: User = Depends(get_admin_user),
) -> User:
    """Require the authenticated admin user to have the superadmin role."""
    if admin_user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return admin_user
