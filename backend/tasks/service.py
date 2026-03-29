"""Background task queue persistence service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func as sa_func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import BackgroundTask


class TaskQueueService:
    """Queue operations for background tasks."""

    @staticmethod
    async def enqueue(
        session: AsyncSession,
        user_id: str,
        task_type: str,
        title: str,
        payload: dict,
        description: str | None = None,
        priority: int = 5,
        scheduled_at: datetime | None = None,
        max_retries: int = 3,
    ) -> dict:
        task = BackgroundTask(
            id=str(uuid4()),
            user_id=user_id,
            task_type=task_type,
            title=title,
            description=description,
            priority=min(max(priority, 1), 10),
            payload_json=json.dumps(payload or {}),
            scheduled_at=scheduled_at,
            max_retries=max_retries,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return _task_to_dict(task)

    @staticmethod
    async def get_task(session: AsyncSession, task_id: str, user_id: str) -> dict | None:
        result = await session.execute(select(BackgroundTask).where(BackgroundTask.id == task_id, BackgroundTask.user_id == user_id))
        t = result.scalar_one_or_none()
        return _task_to_dict(t) if t else None

    @staticmethod
    async def list_tasks(session: AsyncSession, user_id: str, status: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        stmt = select(BackgroundTask).where(BackgroundTask.user_id == user_id)
        if status:
            stmt = stmt.where(BackgroundTask.status == status)
        stmt = stmt.order_by(BackgroundTask.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return [_task_to_dict(t) for t in result.scalars().all()]

    @staticmethod
    async def get_next_runnable(session: AsyncSession) -> BackgroundTask | None:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(BackgroundTask)
            .where(BackgroundTask.status == "queued", (BackgroundTask.scheduled_at.is_(None)) | (BackgroundTask.scheduled_at <= now))
            .order_by(BackgroundTask.priority, BackgroundTask.created_at)
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_progress(session: AsyncSession, task_id: str, progress_pct: int, progress_message: str | None = None) -> None:
        values: dict = {"progress_pct": min(max(progress_pct, 0), 100)}
        if progress_message is not None:
            values["progress_message"] = progress_message
        await session.execute(update(BackgroundTask).where(BackgroundTask.id == task_id).values(**values))
        await session.commit()

    @staticmethod
    async def mark_running(session: AsyncSession, task_id: str) -> None:
        await session.execute(update(BackgroundTask).where(BackgroundTask.id == task_id).values(status="running", started_at=datetime.now(timezone.utc)))
        await session.commit()

    @staticmethod
    async def mark_completed(session: AsyncSession, task_id: str, result: dict | None = None) -> None:
        values: dict = {"status": "completed", "completed_at": datetime.now(timezone.utc), "progress_pct": 100}
        if result is not None:
            values["result_json"] = json.dumps(result)
        await session.execute(update(BackgroundTask).where(BackgroundTask.id == task_id).values(**values))
        await session.commit()

    @staticmethod
    async def mark_failed(session: AsyncSession, task_id: str, error: str) -> None:
        result = await session.execute(select(BackgroundTask).where(BackgroundTask.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            return
        task.retry_count = (task.retry_count or 0) + 1
        if task.retry_count < (task.max_retries or 3):
            task.status = "queued"
            task.error_message = f"Retry {task.retry_count}: {error}"
        else:
            task.status = "failed"
            task.error_message = error
            task.completed_at = datetime.now(timezone.utc)
        await session.commit()

    @staticmethod
    async def cancel_task(session: AsyncSession, task_id: str, user_id: str) -> bool:
        result = await session.execute(
            update(BackgroundTask)
            .where(BackgroundTask.id == task_id, BackgroundTask.user_id == user_id, BackgroundTask.status.in_(["queued", "running", "paused"]))
            .values(status="cancelled", completed_at=datetime.now(timezone.utc))
        )
        await session.commit()
        return bool(result.rowcount)

    @staticmethod
    async def pause_task(session: AsyncSession, task_id: str, user_id: str) -> bool:
        result = await session.execute(
            update(BackgroundTask).where(BackgroundTask.id == task_id, BackgroundTask.user_id == user_id, BackgroundTask.status == "queued").values(status="paused")
        )
        await session.commit()
        return bool(result.rowcount)

    @staticmethod
    async def resume_task(session: AsyncSession, task_id: str, user_id: str) -> bool:
        result = await session.execute(
            update(BackgroundTask).where(BackgroundTask.id == task_id, BackgroundTask.user_id == user_id, BackgroundTask.status == "paused").values(status="queued")
        )
        await session.commit()
        return bool(result.rowcount)

    @staticmethod
    async def get_active_count(session: AsyncSession) -> int:
        result = await session.execute(select(sa_func.count(BackgroundTask.id)).where(BackgroundTask.status == "running"))
        return int(result.scalar() or 0)

    @staticmethod
    async def get_user_badge_count(session: AsyncSession, user_id: str) -> int:
        result = await session.execute(
            select(sa_func.count(BackgroundTask.id)).where(
                BackgroundTask.user_id == user_id,
                BackgroundTask.notification_sent == False,
                BackgroundTask.status.in_(["completed", "failed"]),
            )
        )
        return int(result.scalar() or 0)

    @staticmethod
    async def mark_notifications_sent(session: AsyncSession, user_id: str) -> None:
        await session.execute(
            update(BackgroundTask)
            .where(BackgroundTask.user_id == user_id, BackgroundTask.notification_sent == False, BackgroundTask.status.in_(["completed", "failed"]))
            .values(notification_sent=True)
        )
        await session.commit()


def _task_to_dict(task: BackgroundTask) -> dict:
    return {
        "id": task.id,
        "user_id": task.user_id,
        "task_type": task.task_type,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "payload": json.loads(task.payload_json) if task.payload_json else {},
        "result": json.loads(task.result_json) if task.result_json else None,
        "error_message": task.error_message,
        "progress_pct": task.progress_pct,
        "progress_message": task.progress_message,
        "max_retries": task.max_retries,
        "retry_count": task.retry_count,
        "scheduled_at": task.scheduled_at.isoformat() if task.scheduled_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }
