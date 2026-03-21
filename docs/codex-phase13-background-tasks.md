# Codex Phase 13: Background & Long-Running Tasks

## Project Context
Aegis is a FastAPI + React/TypeScript app. Backend at repo root. Frontend at `frontend/`. Currently, all task execution (task plans from Phase 8, research from Phase 12) happens within the user's active session. If the user closes the browser tab or disconnects, running tasks may be lost. There is no way to queue work for later execution or monitor background jobs.

This phase adds a background task system that:
1. Queues tasks for execution independent of the user's active session
2. Persists task state across server restarts (database-backed)
3. Provides notifications when background tasks complete
4. Allows users to monitor, pause, and cancel background jobs
5. Supports scheduling tasks for future execution

## What to implement
1. `backend/tasks/` module with a task queue, worker, and lifecycle management
2. Database model for background tasks
3. API endpoints for task CRUD, monitoring, and control
4. Frontend task manager panel with status indicators and controls
5. Notification integration (in-app badge + optional webhook)

## CRITICAL RULES
- Do NOT modify: `orchestrator.py`, `session.py`, `navigator.py`, `analyzer.py`, `executor.py`, `mcp_client.py`
- Do NOT modify: any existing file in `backend/providers/`, `backend/connectors/`, `backend/admin/`, `backend/planner/`, `backend/gallery/`, `backend/memory/`, `backend/artifacts/`, `backend/research/`
- Do NOT modify: `backend/credit_rates.py`, `backend/credit_service.py`, `backend/key_management.py`, `backend/conversation_service.py`
- Do NOT modify: any file in `frontend/src/components/settings/`
- Do NOT modify: `frontend/src/components/LandingPage.tsx`, `frontend/src/components/AuthPage.tsx`
- Do NOT modify: `auth.py`
- You MAY add models to `backend/database.py` and router registrations to `main.py`
- Background tasks use an in-process asyncio worker with database persistence (no external queue like Redis/Celery in this phase)
- The worker runs as a background asyncio task started on `startup` event
- ESLint strict: NO `setState` in `useEffect` bodies, NO ref access during render
- Tailwind v4 dark theme: `bg-[#111]`, `bg-[#1a1a1a]`, `border-[#2a2a2a]`, `text-zinc-*`
- Use `apiUrl('/path')` for ALL frontend API calls

---

## Database Model

Add to `backend/database.py` AFTER existing models:

```python
class BackgroundTask(Base):
    """A queued or running background task."""

    __tablename__ = "background_tasks"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    task_type = Column(String(50), nullable=False)  # plan_execution | research | custom
    title = Column(String(500), nullable=False)
    description = Column(Text)
    status = Column(String(20), default="queued", index=True)  # queued | running | paused | completed | failed | cancelled
    priority = Column(Integer, default=5)  # 1 (highest) to 10 (lowest)
    payload_json = Column(Text, nullable=False)  # JSON: task-specific params
    result_json = Column(Text)  # JSON: task result/output
    error_message = Column(Text)
    progress_pct = Column(Integer, default=0)  # 0-100
    progress_message = Column(String(500))
    max_retries = Column(Integer, default=3)
    retry_count = Column(Integer, default=0)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)  # null = run immediately
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    notification_sent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

---

## 1. Create `backend/tasks/__init__.py`

```python
"""Background task queue and worker."""

from .service import TaskQueueService
from .worker import BackgroundWorker

__all__ = ["TaskQueueService", "BackgroundWorker"]
```

## 2. Create `backend/tasks/service.py`

```python
"""Task queue service — CRUD operations for background tasks."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update, delete, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import BackgroundTask

logger = logging.getLogger(__name__)


class TaskQueueService:
    """Manages the background task lifecycle."""

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
        """Add a task to the queue."""
        task = BackgroundTask(
            id=str(uuid4()),
            user_id=user_id,
            task_type=task_type,
            title=title,
            description=description,
            payload_json=json.dumps(payload),
            priority=priority,
            scheduled_at=scheduled_at,
            max_retries=max_retries,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        logger.info("Enqueued task %s (%s) for user %s", task.id, task_type, user_id)
        return _task_to_dict(task)

    @staticmethod
    async def get_task(session: AsyncSession, task_id: str, user_id: str) -> dict | None:
        """Get a single task."""
        result = await session.execute(
            select(BackgroundTask).where(BackgroundTask.id == task_id, BackgroundTask.user_id == user_id)
        )
        t = result.scalar_one_or_none()
        return _task_to_dict(t) if t else None

    @staticmethod
    async def list_tasks(
        session: AsyncSession,
        user_id: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List tasks for a user."""
        stmt = (
            select(BackgroundTask)
            .where(BackgroundTask.user_id == user_id)
            .order_by(BackgroundTask.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(BackgroundTask.status == status)
        result = await session.execute(stmt)
        return [_task_to_dict(t) for t in result.scalars().all()]

    @staticmethod
    async def get_next_runnable(session: AsyncSession) -> BackgroundTask | None:
        """Get the highest-priority queued task that is ready to run."""
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(BackgroundTask)
            .where(
                BackgroundTask.status == "queued",
                (BackgroundTask.scheduled_at.is_(None)) | (BackgroundTask.scheduled_at <= now),
            )
            .order_by(BackgroundTask.priority, BackgroundTask.created_at)
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_progress(
        session: AsyncSession,
        task_id: str,
        progress_pct: int,
        progress_message: str | None = None,
    ) -> None:
        """Update task progress."""
        values: dict = {"progress_pct": min(max(progress_pct, 0), 100)}
        if progress_message is not None:
            values["progress_message"] = progress_message
        await session.execute(
            update(BackgroundTask).where(BackgroundTask.id == task_id).values(**values)
        )
        await session.commit()

    @staticmethod
    async def mark_running(session: AsyncSession, task_id: str) -> None:
        """Mark a task as running."""
        await session.execute(
            update(BackgroundTask)
            .where(BackgroundTask.id == task_id)
            .values(status="running", started_at=datetime.now(timezone.utc))
        )
        await session.commit()

    @staticmethod
    async def mark_completed(session: AsyncSession, task_id: str, result: dict | None = None) -> None:
        """Mark a task as completed."""
        values: dict = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc),
            "progress_pct": 100,
        }
        if result is not None:
            values["result_json"] = json.dumps(result)
        await session.execute(
            update(BackgroundTask).where(BackgroundTask.id == task_id).values(**values)
        )
        await session.commit()

    @staticmethod
    async def mark_failed(session: AsyncSession, task_id: str, error: str) -> None:
        """Mark a task as failed. May retry if retries remain."""
        result = await session.execute(
            select(BackgroundTask).where(BackgroundTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            return

        task.retry_count = (task.retry_count or 0) + 1
        if task.retry_count < (task.max_retries or 3):
            task.status = "queued"
            task.error_message = f"Retry {task.retry_count}: {error}"
            logger.info("Task %s failed, will retry (%d/%d)", task_id, task.retry_count, task.max_retries)
        else:
            task.status = "failed"
            task.error_message = error
            task.completed_at = datetime.now(timezone.utc)
            logger.warning("Task %s failed permanently: %s", task_id, error)
        await session.commit()

    @staticmethod
    async def cancel_task(session: AsyncSession, task_id: str, user_id: str) -> bool:
        """Cancel a queued or running task."""
        result = await session.execute(
            update(BackgroundTask)
            .where(
                BackgroundTask.id == task_id,
                BackgroundTask.user_id == user_id,
                BackgroundTask.status.in_(["queued", "running", "paused"]),
            )
            .values(status="cancelled", completed_at=datetime.now(timezone.utc))
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def pause_task(session: AsyncSession, task_id: str, user_id: str) -> bool:
        """Pause a queued task (removes from runnable pool)."""
        result = await session.execute(
            update(BackgroundTask)
            .where(
                BackgroundTask.id == task_id,
                BackgroundTask.user_id == user_id,
                BackgroundTask.status == "queued",
            )
            .values(status="paused")
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def resume_task(session: AsyncSession, task_id: str, user_id: str) -> bool:
        """Resume a paused task."""
        result = await session.execute(
            update(BackgroundTask)
            .where(
                BackgroundTask.id == task_id,
                BackgroundTask.user_id == user_id,
                BackgroundTask.status == "paused",
            )
            .values(status="queued")
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def get_active_count(session: AsyncSession) -> int:
        """Get the count of currently running tasks."""
        result = await session.execute(
            select(sa_func.count(BackgroundTask.id)).where(BackgroundTask.status == "running")
        )
        return result.scalar() or 0

    @staticmethod
    async def get_user_badge_count(session: AsyncSession, user_id: str) -> int:
        """Get the count of tasks needing user attention (completed but unseen, or failed)."""
        result = await session.execute(
            select(sa_func.count(BackgroundTask.id)).where(
                BackgroundTask.user_id == user_id,
                BackgroundTask.notification_sent == False,
                BackgroundTask.status.in_(["completed", "failed"]),
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def mark_notifications_sent(session: AsyncSession, user_id: str) -> None:
        """Mark all pending notifications as sent for a user."""
        await session.execute(
            update(BackgroundTask)
            .where(
                BackgroundTask.user_id == user_id,
                BackgroundTask.notification_sent == False,
                BackgroundTask.status.in_(["completed", "failed"]),
            )
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
```

## 3. Create `backend/tasks/worker.py`

```python
"""Background worker — polls the task queue and executes tasks.

Runs as a long-lived asyncio task started during the FastAPI startup event.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from backend.database import _session_factory
from backend.tasks.service import TaskQueueService

logger = logging.getLogger(__name__)


class BackgroundWorker:
    """Async background worker that processes queued tasks."""

    def __init__(self, max_concurrent: int = 3, poll_interval: float = 5.0) -> None:
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def start(self) -> None:
        """Start the background worker loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Background worker started (max_concurrent=%d)", self.max_concurrent)

    async def stop(self) -> None:
        """Stop the background worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Background worker stopped")

    async def _loop(self) -> None:
        """Main worker loop — poll queue and execute tasks."""
        while self._running:
            try:
                if not _session_factory:
                    await asyncio.sleep(self.poll_interval)
                    continue

                async with _session_factory() as db:
                    # Check if we have capacity
                    active = await TaskQueueService.get_active_count(db)
                    if active >= self.max_concurrent:
                        await asyncio.sleep(self.poll_interval)
                        continue

                    # Get next runnable task
                    task = await TaskQueueService.get_next_runnable(db)
                    if not task:
                        await asyncio.sleep(self.poll_interval)
                        continue

                    # Mark as running and execute
                    await TaskQueueService.mark_running(db, task.id)

                asyncio.create_task(self._execute_task(task.id, task.task_type, task.payload_json, task.user_id))

            except Exception:
                logger.debug("Worker loop error", exc_info=True)
                await asyncio.sleep(self.poll_interval)

    async def _execute_task(self, task_id: str, task_type: str, payload_json: str, user_id: str) -> None:
        """Execute a single task based on its type."""
        async with self._semaphore:
            try:
                payload = json.loads(payload_json) if payload_json else {}
                handler = TASK_HANDLERS.get(task_type)
                if not handler:
                    raise ValueError(f"Unknown task type: {task_type}")

                result = await handler(task_id, user_id, payload)

                if _session_factory:
                    async with _session_factory() as db:
                        await TaskQueueService.mark_completed(db, task_id, result)

            except Exception as exc:
                logger.warning("Task %s failed: %s", task_id, exc)
                if _session_factory:
                    async with _session_factory() as db:
                        await TaskQueueService.mark_failed(db, task_id, str(exc))


# ── Task handlers ──────────────────────────────────────────────────────
# Each handler receives (task_id, user_id, payload) and returns a result dict.

async def _handle_plan_execution(task_id: str, user_id: str, payload: dict) -> dict:
    """Execute a task plan in the background."""
    plan_id = payload.get("plan_id")
    if not plan_id:
        raise ValueError("plan_id is required")

    from backend.planner.agent_runner import AgentRunner

    async def on_progress(data: dict) -> None:
        if _session_factory and data.get("type") in ("step_completed", "step_failed"):
            async with _session_factory() as db:
                # Calculate approximate progress
                total = data.get("total_steps", 1)
                completed = data.get("completed", 0)
                pct = int((completed / total) * 100) if total else 0
                await TaskQueueService.update_progress(db, task_id, pct, data.get("title", ""))

    runner = AgentRunner(plan_id=plan_id, user_id=user_id, on_step_update=on_progress)
    result = await runner.run()
    return result


async def _handle_research(task_id: str, user_id: str, payload: dict) -> dict:
    """Run deep research in the background."""
    topic = payload.get("topic")
    if not topic:
        raise ValueError("topic is required")

    from backend.research.service import ResearchService
    from backend.key_management import KeyManager
    from config import settings

    provider_name = payload.get("provider", "google")
    model = payload.get("model")

    key_manager = KeyManager(settings.ENCRYPTION_SECRET)
    if _session_factory:
        async with _session_factory() as db:
            api_key = await key_manager.get_key(db, user_id, provider_name)
            if not api_key:
                fallback = {
                    "google": settings.GEMINI_API_KEY,
                    "openai": getattr(settings, "OPENAI_API_KEY", ""),
                    "anthropic": getattr(settings, "ANTHROPIC_API_KEY", ""),
                }
                api_key = fallback.get(provider_name, "")

            async def on_progress(data: dict) -> None:
                phase_pct = {"planning": 10, "searching": 30, "extracting": 60, "synthesizing": 80, "completed": 100}
                pct = phase_pct.get(data.get("phase", ""), 50)
                await TaskQueueService.update_progress(db, task_id, pct, data.get("phase", ""))

            result = await ResearchService.start_research(
                db, user_id, topic, api_key,
                provider_name=provider_name,
                model=model,
                conversation_id=payload.get("conversation_id"),
                on_progress=on_progress,
            )
            return result
    raise ValueError("Database not initialized")


async def _handle_custom(task_id: str, user_id: str, payload: dict) -> dict:
    """Handle a custom task — currently a placeholder.

    In future, this can execute arbitrary user-defined workflows.
    """
    prompt = payload.get("prompt", "")
    # For now, just return the payload as acknowledgment
    return {"status": "completed", "prompt": prompt, "message": "Custom task processing not yet implemented"}


TASK_HANDLERS: dict[str, Any] = {
    "plan_execution": _handle_plan_execution,
    "research": _handle_research,
    "custom": _handle_custom,
}
```

## 4. Create `backend/tasks/router.py`

```python
"""API routes for background task management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import get_session
from backend.tasks.service import TaskQueueService

logger = logging.getLogger(__name__)
task_router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _get_user_uid(request) -> str:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload["uid"]


@task_router.post("/")
async def enqueue_task(
    payload: dict[str, Any],
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Enqueue a background task.

    Body: {
        "task_type": "plan_execution|research|custom",
        "title": "My task",
        "payload": { ... },
        "priority": 5,
        "scheduled_at": "2026-03-21T10:00:00Z"
    }
    """
    uid = _get_user_uid(request)
    task_type = payload.get("task_type", "custom")
    title = payload.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    scheduled_at = None
    if payload.get("scheduled_at"):
        try:
            scheduled_at = datetime.fromisoformat(payload["scheduled_at"].replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid scheduled_at format")

    task = await TaskQueueService.enqueue(
        db, uid,
        task_type=task_type,
        title=title,
        payload=payload.get("payload", {}),
        description=payload.get("description"),
        priority=payload.get("priority", 5),
        scheduled_at=scheduled_at,
        max_retries=payload.get("max_retries", 3),
    )
    return {"ok": True, "task": task}


@task_router.get("/")
async def list_tasks(
    request: Any,
    db: AsyncSession = Depends(get_session),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List user's background tasks."""
    uid = _get_user_uid(request)
    tasks = await TaskQueueService.list_tasks(db, uid, status=status, limit=limit, offset=offset)
    return {"ok": True, "tasks": tasks}


@task_router.get("/badge")
async def task_badge(
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get the notification badge count (completed/failed unseen tasks)."""
    uid = _get_user_uid(request)
    count = await TaskQueueService.get_user_badge_count(db, uid)
    return {"ok": True, "count": count}


@task_router.post("/badge/clear")
async def clear_badge(
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Clear the notification badge."""
    uid = _get_user_uid(request)
    await TaskQueueService.mark_notifications_sent(db, uid)
    return {"ok": True}


@task_router.get("/{task_id}")
async def get_task(
    task_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a single task with full details."""
    uid = _get_user_uid(request)
    task = await TaskQueueService.get_task(db, task_id, uid)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True, "task": task}


@task_router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Cancel a queued or running task."""
    uid = _get_user_uid(request)
    ok = await TaskQueueService.cancel_task(db, task_id, uid)
    if not ok:
        raise HTTPException(status_code=400, detail="Task not found or cannot be cancelled")
    return {"ok": True}


@task_router.post("/{task_id}/pause")
async def pause_task(
    task_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Pause a queued task."""
    uid = _get_user_uid(request)
    ok = await TaskQueueService.pause_task(db, task_id, uid)
    if not ok:
        raise HTTPException(status_code=400, detail="Task not found or not in queued status")
    return {"ok": True}


@task_router.post("/{task_id}/resume")
async def resume_task(
    task_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Resume a paused task."""
    uid = _get_user_uid(request)
    ok = await TaskQueueService.resume_task(db, task_id, uid)
    if not ok:
        raise HTTPException(status_code=400, detail="Task not found or not paused")
    return {"ok": True}
```

## 5. Register router and start worker in `main.py`

Add imports:
```python
from backend.tasks.router import task_router
from backend.tasks.worker import BackgroundWorker
```

Add router registration:
```python
app.include_router(task_router)
```

Create the worker instance at module level (near the top, after app creation):
```python
_background_worker = BackgroundWorker(max_concurrent=3)
```

In the `startup_event` function, add at the end:
```python
await _background_worker.start()
```

In the `shutdown_event` function, add:
```python
await _background_worker.stop()
```

## 6. Create `frontend/src/hooks/useBackgroundTasks.ts`

```typescript
import { useCallback, useState } from 'react'
import { apiUrl } from '../lib/api'

export type BackgroundTaskEntry = {
  id: string
  user_id: string
  task_type: string
  title: string
  description: string | null
  status: 'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled'
  priority: number
  payload: Record<string, unknown>
  result: Record<string, unknown> | null
  error_message: string | null
  progress_pct: number
  progress_message: string | null
  max_retries: number
  retry_count: number
  scheduled_at: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string | null
}

export function useBackgroundTasks() {
  const [tasks, setTasks] = useState<BackgroundTaskEntry[]>([])
  const [badgeCount, setBadgeCount] = useState(0)
  const [loading, setLoading] = useState(false)

  const fetchTasks = useCallback(async (status?: string) => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (status) params.set('status', status)
      const resp = await fetch(apiUrl(`/api/tasks/?${params}`), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setTasks(data.tasks)
    } catch { /* silent */ } finally {
      setLoading(false)
    }
  }, [])

  const fetchBadge = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/tasks/badge'), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setBadgeCount(data.count)
    } catch { /* silent */ }
  }, [])

  const clearBadge = useCallback(async () => {
    try {
      await fetch(apiUrl('/api/tasks/badge/clear'), { method: 'POST', credentials: 'include' })
      setBadgeCount(0)
    } catch { /* silent */ }
  }, [])

  const enqueueTask = useCallback(async (
    taskType: string, title: string, payload: Record<string, unknown>, priority?: number
  ): Promise<BackgroundTaskEntry | null> => {
    try {
      const resp = await fetch(apiUrl('/api/tasks/'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_type: taskType, title, payload, priority }),
      })
      const data = await resp.json()
      if (data.ok) {
        setTasks((prev) => [data.task, ...prev])
        return data.task
      }
      return null
    } catch {
      return null
    }
  }, [])

  const cancelTask = useCallback(async (id: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/tasks/${id}/cancel`), { method: 'POST', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, status: 'cancelled' as const } : t)))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  const pauseTask = useCallback(async (id: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/tasks/${id}/pause`), { method: 'POST', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, status: 'paused' as const } : t)))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  const resumeTask = useCallback(async (id: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/tasks/${id}/resume`), { method: 'POST', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, status: 'queued' as const } : t)))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  return {
    tasks, badgeCount, loading,
    fetchTasks, fetchBadge, clearBadge, enqueueTask, cancelTask, pauseTask, resumeTask,
  }
}
```

## 7. Create `frontend/src/components/TaskManager.tsx`

```tsx
import { useCallback, useEffect } from 'react'
import { useBackgroundTasks } from '../hooks/useBackgroundTasks'
import type { BackgroundTaskEntry } from '../hooks/useBackgroundTasks'

type TaskManagerProps = {
  isOpen: boolean
  onToggle: () => void
}

const STATUS_STYLES: Record<string, { icon: string; color: string; bg: string }> = {
  queued: { icon: '◎', color: 'text-zinc-400', bg: 'bg-zinc-800' },
  running: { icon: '◉', color: 'text-blue-400', bg: 'bg-blue-900/20' },
  paused: { icon: '⏸', color: 'text-amber-400', bg: 'bg-amber-900/20' },
  completed: { icon: '✓', color: 'text-emerald-400', bg: 'bg-emerald-900/20' },
  failed: { icon: '✗', color: 'text-red-400', bg: 'bg-red-900/20' },
  cancelled: { icon: '—', color: 'text-zinc-500', bg: 'bg-zinc-800/50' },
}

export function TaskManager({ isOpen, onToggle }: TaskManagerProps) {
  const {
    tasks, badgeCount, loading,
    fetchTasks, fetchBadge, clearBadge, cancelTask, pauseTask, resumeTask,
  } = useBackgroundTasks()

  useEffect(() => {
    if (isOpen) {
      fetchTasks()
      clearBadge()
    }
  }, [isOpen, fetchTasks, clearBadge])

  // Poll badge count
  useEffect(() => {
    const interval = setInterval(fetchBadge, 30000)
    fetchBadge()
    return () => clearInterval(interval)
  }, [fetchBadge])

  // Poll running tasks
  useEffect(() => {
    if (!isOpen) return
    const hasRunning = tasks.some((t) => t.status === 'running' || t.status === 'queued')
    if (!hasRunning) return
    const interval = setInterval(fetchTasks, 5000)
    return () => clearInterval(interval)
  }, [isOpen, tasks, fetchTasks])

  const renderActions = useCallback((task: BackgroundTaskEntry) => {
    const actions: { label: string; onClick: () => void; color: string }[] = []
    if (task.status === 'running' || task.status === 'queued') {
      actions.push({ label: 'Cancel', onClick: () => cancelTask(task.id), color: 'text-red-400 hover:text-red-300' })
    }
    if (task.status === 'queued') {
      actions.push({ label: 'Pause', onClick: () => pauseTask(task.id), color: 'text-amber-400 hover:text-amber-300' })
    }
    if (task.status === 'paused') {
      actions.push({ label: 'Resume', onClick: () => resumeTask(task.id), color: 'text-blue-400 hover:text-blue-300' })
    }
    return actions
  }, [cancelTask, pauseTask, resumeTask])

  // Toggle button with badge
  if (!isOpen) {
    return (
      <button type="button" onClick={onToggle} className="relative rounded-lg border border-zinc-700 bg-zinc-800 p-2 text-xs text-zinc-400 hover:bg-zinc-700">
        Tasks
        {badgeCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-blue-600 text-[9px] font-bold text-white">
            {badgeCount}
          </span>
        )}
      </button>
    )
  }

  return (
    <div className="flex h-full w-80 shrink-0 flex-col border-l border-[#2a2a2a] bg-[#1a1a1a]">
      <div className="flex items-center justify-between border-b border-[#2a2a2a] px-4 py-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Background Tasks</h3>
        <button type="button" onClick={onToggle} className="text-zinc-500 hover:text-zinc-300">✕</button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {loading && tasks.length === 0 ? (
          <div className="flex justify-center py-8">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          </div>
        ) : tasks.length === 0 ? (
          <p className="py-8 text-center text-xs text-zinc-600">No background tasks</p>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => {
              const ss = STATUS_STYLES[task.status] || STATUS_STYLES.queued
              const actions = renderActions(task)
              return (
                <div key={task.id} className={`rounded-lg border border-zinc-800 ${ss.bg} p-2.5`}>
                  <div className="flex items-start gap-2">
                    <span className={`mt-0.5 text-sm font-mono ${ss.color} ${task.status === 'running' ? 'animate-pulse' : ''}`}>
                      {ss.icon}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium text-zinc-200">{task.title}</p>
                      <div className="mt-0.5 flex items-center gap-2">
                        <span className="text-[10px] text-zinc-600">{task.task_type}</span>
                        {task.progress_message && (
                          <span className="text-[10px] text-zinc-500">{task.progress_message}</span>
                        )}
                      </div>
                      {/* Progress bar for running tasks */}
                      {task.status === 'running' && (
                        <div className="mt-1.5 flex items-center gap-2">
                          <div className="h-1 flex-1 rounded-full bg-zinc-800">
                            <div
                              className="h-1 rounded-full bg-blue-500 transition-all"
                              style={{ width: `${task.progress_pct}%` }}
                            />
                          </div>
                          <span className="text-[9px] text-zinc-600">{task.progress_pct}%</span>
                        </div>
                      )}
                      {task.error_message && (
                        <p className="mt-1 text-[10px] text-red-400 line-clamp-2">{task.error_message}</p>
                      )}
                      {task.retry_count > 0 && task.status !== 'completed' && (
                        <span className="text-[9px] text-amber-500">Retry {task.retry_count}/{task.max_retries}</span>
                      )}
                    </div>
                  </div>
                  {actions.length > 0 && (
                    <div className="mt-1.5 flex gap-2 pl-6">
                      {actions.map((a) => (
                        <button key={a.label} type="button" onClick={a.onClick} className={`text-[10px] ${a.color}`}>
                          {a.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
```

---

## Verification
1. `cd frontend && npm run build` — zero errors
2. `cd frontend && npm run lint` — zero errors
3. Backend starts without import errors
4. BackgroundWorker starts on app startup and stops on shutdown
5. `POST /api/tasks/` creates a queued task
6. `GET /api/tasks/` lists user tasks
7. `GET /api/tasks/badge` returns notification count
8. `POST /api/tasks/{id}/cancel` cancels a task
9. `POST /api/tasks/{id}/pause` pauses a queued task
10. `POST /api/tasks/{id}/resume` resumes a paused task
11. Worker picks up queued tasks and executes them
12. Failed tasks retry up to max_retries before being marked as permanently failed
13. TaskManager renders with progress bars, status icons, and action buttons
14. Badge count updates on completion
