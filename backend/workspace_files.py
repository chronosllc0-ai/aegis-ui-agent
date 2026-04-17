"""User-visible API for global workspace files (read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import User, get_session
from backend.workspace_files_service import list_workspace_files

workspace_files_router = APIRouter(prefix="/api/workspace-files", tags=["workspace-files"])


def _get_current_user(request: Request) -> dict[str, str]:
    from auth import _verify_session

    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    uid = str(payload.get("uid") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"uid": uid}


@workspace_files_router.get("")
async def get_workspace_files(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Return the current global workspace file bundle for any authenticated user."""
    user_payload = _get_current_user(request)
    user = await db.scalar(select(User).where(User.uid == user_payload["uid"]))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return {"files": await list_workspace_files(db)}
