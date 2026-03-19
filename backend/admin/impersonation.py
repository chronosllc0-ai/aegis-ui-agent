"""Admin impersonation API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _sign_session, _verify_session
from backend.admin.audit_service import log_admin_action
from backend.database import ImpersonationSession, User, get_session
from config import settings

async def _get_actor_admin_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Return the acting admin, even when currently impersonating another user."""
    payload = _verify_session(request.cookies.get("aegis_session"))
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")

    actor_uid = payload.get("admin_uid") if payload.get("impersonating") else payload.get("uid")
    if not actor_uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    admin_user = await session.get(User, actor_uid)
    if not admin_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if admin_user.status != "active":
        raise HTTPException(status_code=403, detail="Account suspended")
    if admin_user.role not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Admin access required")
    return admin_user


router = APIRouter(dependencies=[Depends(_get_actor_admin_user)])


class ImpersonationStartRequest(BaseModel):
    """Payload for starting an admin impersonation session."""

    target: str


class ImpersonationTargetUser(BaseModel):
    """Serialized impersonation target user."""

    model_config = ConfigDict(from_attributes=True)

    uid: str
    email: str | None
    name: str | None
    role: str | None
    status: str | None


async def _resolve_target_user(session: AsyncSession, target: str) -> User | None:
    """Resolve a target user by email first, then by uid."""
    normalized_target = target.strip()
    if not normalized_target:
        return None

    email_match = await session.scalar(select(User).where(User.email == normalized_target))
    if email_match:
        return email_match
    return await session.get(User, normalized_target)


def _set_session_cookie(response: JSONResponse, name: str, token: str) -> None:
    """Set a signed session cookie using the standard auth cookie parameters."""
    response.set_cookie(
        name,
        token,
        max_age=int(settings.SESSION_TTL_SECONDS),
        httponly=True,
        secure=bool(settings.COOKIE_SECURE),
        samesite="lax",
        path="/",
    )


@router.post("/start")
async def start_impersonation(
    payload: ImpersonationStartRequest,
    request: Request,
    admin_user: User = Depends(_get_actor_admin_user),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Start impersonating the requested user account."""
    target_user = await _resolve_target_user(session, payload.target)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    if target_user.uid == admin_user.uid:
        raise HTTPException(status_code=400, detail="Cannot impersonate yourself")
    if target_user.role == "superadmin":
        raise HTTPException(status_code=403, detail="Cannot impersonate a superadmin")

    impersonation_session = ImpersonationSession(
        admin_id=admin_user.uid,
        target_user_id=target_user.uid,
    )
    session.add(impersonation_session)
    await session.flush()

    current_session_token = request.cookies.get("aegis_session")
    current_session_payload = _verify_session(current_session_token)
    if not current_session_token or not current_session_payload:
        raise HTTPException(status_code=401, detail="Not authenticated")

    impersonated_payload: dict[str, Any] = {
        "uid": target_user.uid,
        "provider": target_user.provider,
        "provider_id": target_user.provider_id,
        "email": target_user.email,
        "name": target_user.name,
        "avatar_url": target_user.avatar_url,
        "role": target_user.role or "user",
        "status": target_user.status or "active",
        "created_at": target_user.created_at,
        "last_login_at": target_user.last_login_at,
        "impersonating": True,
        "admin_uid": admin_user.uid,
    }
    impersonated_token = _sign_session(impersonated_payload)

    await log_admin_action(
        session,
        admin_id=admin_user.uid,
        action="impersonate.start",
        target_user_id=target_user.uid,
        details={
            "impersonation_session_id": impersonation_session.id,
            "target": payload.target,
        },
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    await session.refresh(impersonation_session)

    response = JSONResponse(
        {
            "ok": True,
            "impersonating": True,
            "target_user": ImpersonationTargetUser.model_validate(target_user).model_dump(mode="json"),
            "admin_uid": admin_user.uid,
            "impersonation_session_id": impersonation_session.id,
        }
    )
    _set_session_cookie(response, "aegis_admin_session", current_session_token)
    _set_session_cookie(response, "aegis_session", impersonated_token)
    return response


@router.post("/stop")
async def stop_impersonation(
    request: Request,
    admin_user: User = Depends(_get_actor_admin_user),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Stop the current impersonation session and restore the admin session."""
    current_payload = _verify_session(request.cookies.get("aegis_session")) or {}
    restored_session_token = request.cookies.get("aegis_admin_session")
    restored_payload = _verify_session(restored_session_token)
    if not restored_session_token or not restored_payload:
        raise HTTPException(status_code=401, detail="No admin session to restore")

    active_session = await session.scalar(
        select(ImpersonationSession)
        .where(
            ImpersonationSession.admin_id == restored_payload.get("uid"),
            ImpersonationSession.ended_at.is_(None),
        )
        .order_by(ImpersonationSession.started_at.desc())
        .limit(1)
    )
    if active_session:
        active_session.ended_at = datetime.now(timezone.utc)
        await session.flush()

    await log_admin_action(
        session,
        admin_id=restored_payload.get("uid", admin_user.uid),
        action="impersonate.stop",
        target_user_id=current_payload.get("uid") if current_payload.get("impersonating") else None,
        details={
            "impersonation_session_id": active_session.id if active_session else None,
            "restored_admin_uid": restored_payload.get("uid"),
        },
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()

    response = JSONResponse({"ok": True, "impersonating": False, "admin_uid": restored_payload.get("uid")})
    _set_session_cookie(response, "aegis_session", restored_session_token)
    response.delete_cookie("aegis_admin_session", path="/")
    return response


@router.get("/status")
async def impersonation_status(request: Request) -> dict[str, Any]:
    """Return whether the current session is an impersonated session."""
    payload = _verify_session(request.cookies.get("aegis_session"))
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")

    response: dict[str, Any] = {"impersonating": bool(payload.get("impersonating"))}
    if payload.get("impersonating"):
        response["target_user"] = {
            "uid": payload.get("uid"),
            "email": payload.get("email"),
            "name": payload.get("name"),
            "role": payload.get("role"),
            "status": payload.get("status"),
        }
        response["admin_uid"] = payload.get("admin_uid")
    return response
