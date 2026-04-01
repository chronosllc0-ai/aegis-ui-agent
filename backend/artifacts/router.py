"""API routes for artifact management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.artifacts.service import ArtifactService
from backend.database import get_session

artifact_router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


def _get_user_uid(request: Request) -> str:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload["uid"]


@artifact_router.get("/")
async def list_artifacts(
    request: Request,
    db: AsyncSession = Depends(get_session),
    conversation_id: str | None = Query(None),
    artifact_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    uid = _get_user_uid(request)
    artifacts = await ArtifactService.list_artifacts(db, uid, conversation_id, artifact_type, limit, offset)
    return {"ok": True, "artifacts": artifacts}


@artifact_router.get("/{artifact_id}")
async def get_artifact(artifact_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    artifact = await ArtifactService.get_artifact(db, artifact_id, uid)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"ok": True, "artifact": artifact}


@artifact_router.get("/{artifact_id}/download", response_model=None)
async def download_artifact(
    artifact_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> Response:
    uid = _get_user_uid(request)

    # Try S3 pre-signed URL first
    presigned_url = await ArtifactService.get_download_url(db, artifact_id, uid)
    if presigned_url:
        return RedirectResponse(url=presigned_url, status_code=302)

    # Fall back to local file
    path = await ArtifactService.get_file_path(db, artifact_id, uid)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(path, filename=path.name.split("_", 1)[-1])


@artifact_router.delete("/{artifact_id}")
async def delete_artifact(artifact_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    ok = await ArtifactService.delete_artifact(db, artifact_id, uid)
    if not ok:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"ok": True}
