"""Automation / scheduled-task API endpoints.

Mounted at ``/api/automation/``:

- ``GET  /api/automation/tasks``                — list user's tasks
- ``POST /api/automation/tasks``                — create a task
- ``GET  /api/automation/tasks/{task_id}``      — get a single task
- ``PATCH /api/automation/tasks/{task_id}``     — update a task
- ``DELETE /api/automation/tasks/{task_id}``    — delete a task
- ``POST /api/automation/tasks/{task_id}/run``  — trigger an immediate run
- ``GET  /api/automation/tasks/{task_id}/runs`` — run history (last 20)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import ScheduledTask, get_session

logger = logging.getLogger(__name__)

automation_router = APIRouter(prefix="/api/automation", tags=["automation"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CRON_PATTERN = re.compile(
    r"^(\*|[0-9]{1,2}(?:-[0-9]{1,2})?(?:,[0-9]{1,2}(?:-[0-9]{1,2})?)*|[0-9]{1,2}/[0-9]{1,2}|\*/[0-9]{1,2})"
    r"\s+"
    r"(\*|[0-9]{1,2}(?:-[0-9]{1,2})?(?:,[0-9]{1,2}(?:-[0-9]{1,2})?)*|[0-9]{1,2}/[0-9]{1,2}|\*/[0-9]{1,2})"
    r"\s+"
    r"(\*|[0-9]{1,2}(?:-[0-9]{1,2})?(?:,[0-9]{1,2}(?:-[0-9]{1,2})?)*|[0-9]{1,2}/[0-9]{1,2}|\*/[0-9]{1,2})"
    r"\s+"
    r"(\*|[0-9]{1,2}(?:-[0-9]{1,2})?(?:,[0-9]{1,2}(?:-[0-9]{1,2})?)*|[0-9]{1,2}/[0-9]{1,2}|\*/[0-9]{1,2})"
    r"\s+"
    r"(\*|[0-6](?:-[0-6])?(?:,[0-6](?:-[0-6])?)*|[0-6]/[0-9]{1,2}|\*/[0-9]{1,2})"
    r"$"
)


def _validate_cron(expr: str) -> str:
    """Raise ValueError if *expr* is not a valid 5-field cron expression."""
    if not _CRON_PATTERN.match(expr.strip()):
        raise ValueError(f"Invalid cron expression: {expr!r}")
    return expr.strip()


def _compute_next_run(cron_expr: str, tz_name: str) -> datetime | None:
    """Compute the next scheduled run time using ``croniter``."""
    try:
        from croniter import croniter  # type: ignore[import-untyped]
        import zoneinfo

        tz = zoneinfo.ZoneInfo(tz_name)
        now = datetime.now(tz)
        it = croniter(cron_expr, now)
        next_dt: datetime = it.get_next(datetime)
        # Make timezone-aware
        if next_dt.tzinfo is None:
            next_dt = next_dt.replace(tzinfo=tz)
        return next_dt.astimezone(timezone.utc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not compute next_run_at for cron %r: %s", cron_expr, exc)
        return None


def _task_to_dict(task: ScheduledTask) -> dict[str, Any]:
    execution_target_type = task.execution_target_type or "assistant_prompt"
    assistant_task_prompt = task.prompt if execution_target_type == "assistant_prompt" else None
    workflow_id = task.workflow_id if execution_target_type == "saved_workflow" else None
    return {
        "id": task.id,
        "user_id": task.user_id,
        "name": task.name,
        "description": task.description,
        "execution_target_type": execution_target_type,
        "assistant_task_prompt": assistant_task_prompt,
        "workflow_id": workflow_id,
        "session_scope": task.session_scope or "main",
        "wake_mode": task.wake_mode or "now",
        "delivery_channel": task.delivery_channel or "chat",
        "prompt": task.prompt if execution_target_type == "assistant_prompt" else None,
        "cron_expr": task.cron_expr,
        "timezone": task.timezone,
        "enabled": task.enabled,
        "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
        "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
        "last_status": task.last_status,
        "last_run_status": task.last_status,
        "last_error": task.last_error,
        "run_count": task.run_count,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _get_current_user(request: Request) -> dict[str, Any]:
    from auth import _verify_session

    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class TaskCreate(BaseModel):
    name: str
    description: str | None = None
    execution_target_type: Literal["assistant_prompt", "saved_workflow"] = "assistant_prompt"
    assistant_task_prompt: str | None = None
    workflow_id: str | None = None
    prompt: str | None = None  # legacy alias for assistant_task_prompt
    cron_expr: str
    timezone: str = "UTC"
    session_scope: Literal["main", "isolated"] = "main"
    wake_mode: Literal["now", "next-heartbeat", "scheduled"] = "now"
    delivery_channel: str = "chat"

    @field_validator("cron_expr")
    @classmethod
    def validate_cron_expr(cls, v: str) -> str:
        try:
            return _validate_cron(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def validate_target_fields(self) -> "TaskCreate":
        prompt_value = self.assistant_task_prompt or self.prompt
        if self.execution_target_type == "assistant_prompt":
            if not prompt_value or not prompt_value.strip():
                raise ValueError("assistant_task_prompt is required for execution_target_type=assistant_prompt")
            self.assistant_task_prompt = prompt_value.strip()
            self.prompt = prompt_value.strip()
            self.workflow_id = None
            return self

        if not self.workflow_id or not self.workflow_id.strip():
            raise ValueError("workflow_id is required for execution_target_type=saved_workflow")
        self.workflow_id = self.workflow_id.strip()
        self.assistant_task_prompt = None
        self.prompt = None
        return self


class TaskUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    execution_target_type: Literal["assistant_prompt", "saved_workflow"] | None = None
    assistant_task_prompt: str | None = None
    workflow_id: str | None = None
    prompt: str | None = None
    cron_expr: str | None = None
    timezone: str | None = None
    enabled: bool | None = None
    session_scope: Literal["main", "isolated"] | None = None
    wake_mode: Literal["now", "next-heartbeat", "scheduled"] | None = None
    delivery_channel: str | None = None

    @field_validator("cron_expr")
    @classmethod
    def validate_cron_expr(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            return _validate_cron(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


def _validate_target_update(
    task: ScheduledTask,
    body: TaskUpdate,
) -> tuple[str, str, str | None]:
    """Validate create/update target fields and return normalized values."""
    execution_target_type = body.execution_target_type or task.execution_target_type or "assistant_prompt"
    existing_prompt = task.prompt if (task.execution_target_type or "assistant_prompt") == "assistant_prompt" else ""
    prompt_value = body.assistant_task_prompt
    if prompt_value is None or not prompt_value.strip():
        prompt_value = body.prompt
    if prompt_value is None or not str(prompt_value).strip():
        prompt_value = existing_prompt

    workflow_id = body.workflow_id if body.workflow_id is not None else task.workflow_id

    if execution_target_type == "assistant_prompt":
        if not prompt_value or not prompt_value.strip():
            raise HTTPException(
                status_code=422,
                detail="assistant_task_prompt is required for execution_target_type=assistant_prompt",
            )
        return execution_target_type, prompt_value.strip(), None

    if not workflow_id or not workflow_id.strip():
        raise HTTPException(status_code=422, detail="workflow_id is required for execution_target_type=saved_workflow")
    return execution_target_type, "", workflow_id.strip()


# ---------------------------------------------------------------------------
# In-memory run history (simple ring buffer per task_id)
# ---------------------------------------------------------------------------

_run_history: dict[str, list[dict[str, Any]]] = {}
_MAX_HISTORY = 20


def _record_run(task_id: str, entry: dict[str, Any]) -> None:
    buf = _run_history.setdefault(task_id, [])
    buf.insert(0, entry)
    if len(buf) > _MAX_HISTORY:
        buf.pop()


def _parse_history_ts(entry: dict[str, Any]) -> datetime | None:
    ts_value = entry.get("started_at") or entry.get("finished_at")
    if not isinstance(ts_value, str) or not ts_value:
        return None
    try:
        return datetime.fromisoformat(ts_value)
    except ValueError:
        return None


def _normalize_datetime(value: datetime) -> datetime:
    """Normalize parsed datetimes to timezone-aware UTC for safe comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@automation_router.get("/tasks")
async def list_tasks(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    user = _get_current_user(request)
    result = await session.execute(
        select(ScheduledTask)
        .where(ScheduledTask.user_id == user["uid"])
        .order_by(ScheduledTask.created_at.desc())
    )
    tasks = result.scalars().all()
    return {"tasks": [_task_to_dict(t) for t in tasks]}


@automation_router.post("/tasks")
async def create_task(
    body: TaskCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    user = _get_current_user(request)
    next_run = _compute_next_run(body.cron_expr, body.timezone)
    task = ScheduledTask(
        user_id=user["uid"],
        name=body.name,
        description=body.description,
        execution_target_type=body.execution_target_type,
        prompt=body.prompt or body.assistant_task_prompt or "",
        workflow_id=body.workflow_id,
        session_scope=body.session_scope,
        wake_mode=body.wake_mode,
        delivery_channel=(body.delivery_channel or "chat").strip() or "chat",
        cron_expr=body.cron_expr,
        timezone=body.timezone,
        enabled=True,
        next_run_at=next_run,
        last_status="pending",
        run_count=0,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return {"task": _task_to_dict(task)}


@automation_router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    user = _get_current_user(request)
    task = await session.get(ScheduledTask, task_id)
    if not task or task.user_id != user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": _task_to_dict(task)}


@automation_router.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    body: TaskUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    user = _get_current_user(request)
    task = await session.get(ScheduledTask, task_id)
    if not task or task.user_id != user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found")

    execution_target_type, normalized_prompt, normalized_workflow_id = _validate_target_update(task, body)
    task.execution_target_type = execution_target_type
    task.prompt = normalized_prompt
    task.workflow_id = normalized_workflow_id

    if body.name is not None:
        task.name = body.name
    if body.description is not None:
        task.description = body.description
    if body.enabled is not None:
        task.enabled = body.enabled
    if body.timezone is not None:
        task.timezone = body.timezone
    if body.session_scope is not None:
        task.session_scope = body.session_scope
    if body.wake_mode is not None:
        task.wake_mode = body.wake_mode
    if body.delivery_channel is not None:
        task.delivery_channel = body.delivery_channel.strip() or "chat"

    cron_changed = body.cron_expr is not None
    if cron_changed:
        task.cron_expr = body.cron_expr  # type: ignore[assignment]

    tz = body.timezone if body.timezone is not None else task.timezone
    if cron_changed or body.timezone is not None:
        task.next_run_at = _compute_next_run(task.cron_expr, tz)

    await session.commit()
    await session.refresh(task)
    return {"task": _task_to_dict(task)}


@automation_router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    user = _get_current_user(request)
    task = await session.get(ScheduledTask, task_id)
    if not task or task.user_id != user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found")
    await session.delete(task)
    await session.commit()
    _run_history.pop(task_id, None)
    return {"ok": True}


@automation_router.post("/tasks/{task_id}/run")
async def trigger_run(
    task_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Trigger an immediate (fire-and-forget) run of the task."""
    user = _get_current_user(request)
    task = await session.get(ScheduledTask, task_id)
    if not task or task.user_id != user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found")

    # Fire and forget — import task_runner to reuse execution logic
    import asyncio
    from backend import task_runner

    asyncio.create_task(task_runner.execute_task(task_id))
    return {"ok": True, "message": "Task execution triggered"}


@automation_router.get("/tasks/{task_id}/runs")
async def get_run_history(
    task_id: str,
    request: Request,
    status: Literal["pending", "running", "success", "failed"] | None = Query(default=None),
    scope: Literal["main", "isolated"] | None = Query(default=None),
    delivery_channel: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    user = _get_current_user(request)
    task = await session.get(ScheduledTask, task_id)
    if not task or task.user_id != user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found")
    history = _run_history.get(task_id, [])
    # TODO: run history is currently an in-memory ring buffer; if this grows beyond
    # small operational size, migrate history + filtering to DB-backed queries.
    normalized_date_from = _normalize_datetime(date_from) if date_from is not None else None
    normalized_date_to = _normalize_datetime(date_to) if date_to is not None else None
    if status is not None:
        history = [entry for entry in history if entry.get("status") == status]
    if scope is not None:
        history = [entry for entry in history if entry.get("session_scope") == scope]
    if delivery_channel is not None:
        normalized_channel = delivery_channel.strip().lower()
        history = [entry for entry in history if str(entry.get("delivery_channel", "")).lower() == normalized_channel]
    if normalized_date_from is not None:
        history = [
            entry
            for entry in history
            if (parsed_ts := _parse_history_ts(entry)) is not None and _normalize_datetime(parsed_ts) >= normalized_date_from
        ]
    if normalized_date_to is not None:
        history = [
            entry
            for entry in history
            if (parsed_ts := _parse_history_ts(entry)) is not None and _normalize_datetime(parsed_ts) <= normalized_date_to
        ]
    return {"runs": history}
