"""Admin endpoints for cloud agent task management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.dependencies import get_admin_user
from backend.database import AgentAction, AgentTask, User, get_session
from backend.agent_spawn import update_task_status

router = APIRouter(prefix="/agents", tags=["admin-agents"])


@router.get("/tasks")
async def admin_list_tasks(
    user_id: str | None = None,
    status: str | None = None,
    platform: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List all agent tasks (admin view) with optional filters."""
    _ = admin
    query = select(AgentTask)
    if user_id:
        query = query.where(AgentTask.user_id == user_id)
    if status:
        query = query.where(AgentTask.status == status)
    if platform:
        query = query.where(AgentTask.platform == platform)
    query = query.order_by(desc(AgentTask.created_at)).limit(limit).offset(offset)

    count_query = select(func.count()).select_from(AgentTask)
    if user_id:
        count_query = count_query.where(AgentTask.user_id == user_id)
    if status:
        count_query = count_query.where(AgentTask.status == status)
    if platform:
        count_query = count_query.where(AgentTask.platform == platform)

    result = await db.execute(query)
    tasks = list(result.scalars().all())
    total = (await db.execute(count_query)).scalar() or 0

    return {
        "tasks": [
            {
                "id": t.id,
                "user_id": t.user_id,
                "instruction": t.instruction[:200],
                "status": t.status,
                "platform": t.platform,
                "agent_type": t.agent_type,
                "provider": t.provider,
                "model": t.model,
                "sandbox_id": t.sandbox_id,
                "credits_used": t.credits_used,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/tasks/{task_id}")
async def admin_get_task(
    task_id: str,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get full task details including all actions."""
    _ = admin
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    actions_result = await db.execute(
        select(AgentAction).where(AgentAction.task_id == task_id).order_by(AgentAction.sequence)
    )
    actions = list(actions_result.scalars().all())

    return {
        "id": task.id,
        "user_id": task.user_id,
        "instruction": task.instruction,
        "status": task.status,
        "platform": task.platform,
        "agent_type": task.agent_type,
        "provider": task.provider,
        "model": task.model,
        "sandbox_id": task.sandbox_id,
        "result_summary": task.result_summary,
        "error_message": task.error_message,
        "credits_used": task.credits_used,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "actions": [
            {
                "id": a.id,
                "sequence": a.sequence,
                "action_type": a.action_type,
                "description": a.description,
                "input_data": a.input_data,
                "output_data": a.output_data,
                "duration_ms": a.duration_ms,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in actions
        ],
    }


@router.post("/tasks/{task_id}/cancel")
async def admin_cancel_task(
    task_id: str,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Force-cancel any agent task (admin power)."""
    _ = admin
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in ("completed", "failed", "cancelled"):
        return {"task_id": task_id, "status": task.status, "message": "Task already terminated"}

    updated = await update_task_status(db, task_id, "cancelled")
    return {"task_id": task_id, "status": updated.status if updated else "cancelled"}


@router.get("/stats")
async def admin_agent_stats(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Dashboard stats for agent tasks."""
    _ = admin
    total = (await db.execute(select(func.count()).select_from(AgentTask))).scalar() or 0
    running = (
        await db.execute(select(func.count()).select_from(AgentTask).where(AgentTask.status == "running"))
    ).scalar() or 0
    pending = (
        await db.execute(select(func.count()).select_from(AgentTask).where(AgentTask.status == "pending"))
    ).scalar() or 0
    completed = (
        await db.execute(select(func.count()).select_from(AgentTask).where(AgentTask.status == "completed"))
    ).scalar() or 0
    failed = (
        await db.execute(select(func.count()).select_from(AgentTask).where(AgentTask.status == "failed"))
    ).scalar() or 0

    total_credits = (await db.execute(select(func.coalesce(func.sum(AgentTask.credits_used), 0)))).scalar() or 0

    platform_counts_result = await db.execute(select(AgentTask.platform, func.count()).group_by(AgentTask.platform))
    platforms = {row[0]: row[1] for row in platform_counts_result.all()}

    return {
        "total": total,
        "running": running,
        "pending": pending,
        "completed": completed,
        "failed": failed,
        "total_credits_used": total_credits,
        "by_platform": platforms,
    }
