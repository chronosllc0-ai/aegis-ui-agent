"""Workspace-file API with scoped global and per-user layers."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import auth
from backend.database import User, get_session
from backend.workspace_files_service import (
    WORKSPACE_FILE_NAMES,
    delete_user_workspace_file_override,
    get_effective_workspace_file,
    list_global_workspace_files,
    list_user_workspace_files,
    upsert_global_workspace_file,
    upsert_user_workspace_file,
)

workspace_files_router = APIRouter(prefix="/api/workspace", tags=["workspace-files"])


class PutWorkspaceFileBody(BaseModel):
    content: str


async def _get_current_user(request: Request, db: AsyncSession) -> User:
    token = request.cookies.get("aegis_session")
    payload = auth._verify_session(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    uid = str(payload.get("uid") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await db.scalar(select(User).where(User.uid == uid))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account suspended")
    return user


@workspace_files_router.get("/files")
async def get_workspace_files(
    request: Request,
    scope: Literal["user", "global"] = Query(default="user"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """List workspace files by scope."""
    user = await _get_current_user(request, db)
    if scope == "global":
        return {"scope": scope, "files": await list_global_workspace_files(db), "supported_files": list(WORKSPACE_FILE_NAMES)}
    return {"scope": scope, "files": await list_user_workspace_files(db, user.uid), "supported_files": list(WORKSPACE_FILE_NAMES)}


@workspace_files_router.put("/files/{name}")
async def put_workspace_file(
    name: str,
    body: PutWorkspaceFileBody,
    request: Request,
    scope: Literal["user", "global"] = Query(default="user"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Write workspace file content to selected scope with RBAC checks."""
    user = await _get_current_user(request, db)
    content = body.content
    try:
        if scope == "global":
            if user.role not in {"admin", "superadmin"}:
                raise HTTPException(status_code=403, detail="Admin access required")
            file_payload = await upsert_global_workspace_file(
                db,
                file_name=name,
                content=content,
                actor_id=user.uid,
                operation="edit",
            )
        else:
            file_payload = await upsert_user_workspace_file(
                db,
                user_id=user.uid,
                file_name=name,
                content=content,
                actor_id=user.uid,
                operation="edit",
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"scope": scope, "file": file_payload}


@workspace_files_router.delete("/files/{name}")
async def delete_workspace_file(
    name: str,
    request: Request,
    scope: Literal["user", "global"] = Query(default="user"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Delete user override to revert to global. Global delete is not supported."""
    user = await _get_current_user(request, db)
    if scope != "user":
        raise HTTPException(status_code=400, detail="Only scope=user delete is supported")
    try:
        await delete_user_workspace_file_override(db, user_id=user.uid, file_name=name, actor_id=user.uid)
        file_payload = await get_effective_workspace_file(db, user.uid, name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"scope": "user", "file": file_payload}


# Backward-compatible alias for older clients.
legacy_workspace_files_router = APIRouter(prefix="/api/workspace-files", tags=["workspace-files-legacy"])


@legacy_workspace_files_router.get("")
async def get_workspace_files_legacy(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    user = await _get_current_user(request, db)
    return {"files": await list_user_workspace_files(db, user.uid)}
