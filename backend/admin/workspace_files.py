"""Admin APIs for globally managed runtime workspace files."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.audit_service import log_admin_action
from backend.admin.dependencies import get_admin_user
from backend.database import User, get_session
from backend.workspace_files_service import WORKSPACE_FILE_NAMES, list_workspace_files, upsert_workspace_files

router = APIRouter(prefix="/workspace-files", tags=["admin-workspace-files"])


class PatchWorkspaceFilesBody(BaseModel):
    files: dict[str, str]


@router.get("")
async def get_admin_workspace_files(
    request: Request,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    _ = request
    _ = admin
    return {"files": await list_workspace_files(db), "supported_files": list(WORKSPACE_FILE_NAMES)}


@router.patch("")
async def patch_admin_workspace_files(
    body: PatchWorkspaceFilesBody,
    request: Request,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    try:
        files = await upsert_workspace_files(db, body.files, admin.uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await log_admin_action(
        db,
        admin_id=admin.uid,
        action="workspace_files.admin_edit",
        details={"updated_files": sorted(body.files.keys())},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"files": files, "supported_files": list(WORKSPACE_FILE_NAMES)}
