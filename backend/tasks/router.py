"""API routes for background tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import get_session
from backend.tasks.service import TaskQueueService

task_router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _get_user_uid(request: Request) -> str:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload["uid"]


@task_router.post("/")
async def enqueue_task(payload: dict[str, Any], request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    task_type = str(payload.get("task_type", "custom"))
    title = str(payload.get("title", "")).strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    scheduled_at = None
    if payload.get("scheduled_at"):
        try:
            scheduled_at = datetime.fromisoformat(str(payload["scheduled_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid scheduled_at format") from exc
    task = await TaskQueueService.enqueue(
        db,
        uid,
        task_type=task_type,
        title=title,
        payload=payload.get("payload", {}),
        description=payload.get("description"),
        priority=int(payload.get("priority", 5)),
        scheduled_at=scheduled_at,
        max_retries=int(payload.get("max_retries", 3)),
    )
    return {"ok": True, "task": task}


@task_router.get("/")
async def list_tasks(
    request: Request,
    db: AsyncSession = Depends(get_session),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    uid = _get_user_uid(request)
    tasks = await TaskQueueService.list_tasks(db, uid, status=status, limit=limit, offset=offset)
    return {"ok": True, "tasks": tasks}


@task_router.get("/badge")
async def task_badge(request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    count = await TaskQueueService.get_user_badge_count(db, uid)
    return {"ok": True, "count": count}


@task_router.post("/badge/clear")
async def clear_badge(request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    await TaskQueueService.mark_notifications_sent(db, uid)
    return {"ok": True}


@task_router.get("/{task_id}")
async def get_task(task_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    task = await TaskQueueService.get_task(db, task_id, uid)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True, "task": task}


@task_router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    ok = await TaskQueueService.cancel_task(db, task_id, uid)
    if not ok:
        raise HTTPException(status_code=400, detail="Task not found or cannot be cancelled")
    return {"ok": True}


@task_router.post("/{task_id}/pause")
async def pause_task(task_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    ok = await TaskQueueService.pause_task(db, task_id, uid)
    if not ok:
        raise HTTPException(status_code=400, detail="Task not found or not in queued status")
    return {"ok": True}


@task_router.post("/{task_id}/resume")
async def resume_task(task_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    ok = await TaskQueueService.resume_task(db, task_id, uid)
    if not ok:
        raise HTTPException(status_code=400, detail="Task not found or not in paused status")
    return {"ok": True}
