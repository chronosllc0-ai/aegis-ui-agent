"""API routes for artifact management and download."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.artifacts.service import ArtifactService
from backend.database import get_session

artifact_router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


def _get_user_uid(request: Request) -> str:
    payload = _verify_session(request.cookies.get("aegis_session"))
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload["uid"]


@artifact_router.get("/")
async def list_artifacts(
    request: Request,
    db: AsyncSession = Depends(get_session),
    conversation_id: str | None = Query(None),
    artifact_type: str | None = Query(None, alias="type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    uid = _get_user_uid(request)
    artifacts = await ArtifactService.list_artifacts(db, uid, conversation_id, artifact_type, limit, offset)
    return {"ok": True, "artifacts": artifacts}


@artifact_router.post("/")
async def create_artifact(payload: dict[str, Any], request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    title = str(payload.get("title", "")).strip()
    content = payload.get("content", "")
    if not title or content == "":
        raise HTTPException(status_code=400, detail="Title and content are required")
    artifact = await ArtifactService.create(
        db,
        uid,
        title=title,
        content=content,
        artifact_type=payload.get("artifact_type", "document"),
        filename=payload.get("filename"),
        description=payload.get("description"),
        conversation_id=payload.get("conversation_id"),
        plan_id=payload.get("plan_id"),
        step_id=payload.get("step_id"),
        language=payload.get("language"),
        metadata=payload.get("metadata"),
    )
    return {"ok": True, "artifact": artifact}


@artifact_router.get("/{artifact_id}")
async def get_artifact(artifact_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    artifact = await ArtifactService.get(db, artifact_id, uid)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"ok": True, "artifact": artifact}


@artifact_router.get("/{artifact_id}/download")
async def download_artifact(artifact_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> FileResponse:
    uid = _get_user_uid(request)
    artifact = await ArtifactService.get(db, artifact_id, uid)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    file_path = ArtifactService.get_file_path(artifact)
    if not file_path:
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")
    await ArtifactService.record_download(db, artifact_id)
    return FileResponse(path=str(file_path), filename=artifact["filename"], media_type=artifact["mime_type"])


@artifact_router.post("/{artifact_id}/pin")
async def toggle_pin(artifact_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    artifact = await ArtifactService.toggle_pin(db, artifact_id, uid)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"ok": True, "artifact": artifact}


@artifact_router.delete("/{artifact_id}")
async def delete_artifact(artifact_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    ok = await ArtifactService.delete_artifact(db, artifact_id, uid)
    if not ok:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"ok": True}
