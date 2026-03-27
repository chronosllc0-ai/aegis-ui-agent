"""Cloud agent spawning service — creates and tracks agent tasks from any channel."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AgentAction, AgentTask

logger = logging.getLogger(__name__)


async def create_agent_task(
    db: AsyncSession,
    *,
    user_id: str,
    instruction: str,
    platform: str,
    platform_chat_id: str | None = None,
    platform_message_id: str | None = None,
    agent_type: str = "navigator",
    provider: str | None = None,
    model: str | None = None,
) -> AgentTask:
    """Create a new agent task record."""
    task = AgentTask(
        id=str(uuid4()),
        user_id=user_id,
        platform=platform,
        platform_chat_id=platform_chat_id,
        platform_message_id=platform_message_id,
        instruction=instruction,
        status="pending",
        agent_type=agent_type,
        provider=provider,
        model=model,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    logger.info("Agent task created: %s (platform=%s, user=%s)", task.id, platform, user_id)
    return task


async def update_task_status(
    db: AsyncSession,
    task_id: str,
    status: str,
    *,
    result_summary: str | None = None,
    error_message: str | None = None,
    credits_used: int | None = None,
    sandbox_id: str | None = None,
) -> AgentTask | None:
    """Update an agent task's status."""
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return None

    task.status = status
    now = datetime.now(timezone.utc)

    if status == "running" and not task.started_at:
        task.started_at = now
    if status in ("completed", "failed", "cancelled"):
        task.completed_at = now
    if result_summary is not None:
        task.result_summary = result_summary
    if error_message is not None:
        task.error_message = error_message
    if credits_used is not None:
        task.credits_used = credits_used
    if sandbox_id is not None:
        task.sandbox_id = sandbox_id

    await db.commit()
    await db.refresh(task)
    return task


async def log_agent_action(
    db: AsyncSession,
    *,
    task_id: str,
    sequence: int,
    action_type: str,
    description: str | None = None,
    input_data: str | None = None,
    output_data: str | None = None,
    duration_ms: int | None = None,
) -> AgentAction:
    """Log an individual agent action."""
    action = AgentAction(
        id=str(uuid4()),
        task_id=task_id,
        sequence=sequence,
        action_type=action_type,
        description=description,
        input_data=input_data,
        output_data=output_data,
        duration_ms=duration_ms,
    )
    db.add(action)
    await db.commit()
    return action


async def get_user_tasks(
    db: AsyncSession,
    user_id: str,
    *,
    status: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentTask]:
    """Get tasks for a user, optionally filtered by status/platform."""
    query = select(AgentTask).where(AgentTask.user_id == user_id)
    if status:
        query = query.where(AgentTask.status == status)
    if platform:
        query = query.where(AgentTask.platform == platform)
    query = query.order_by(desc(AgentTask.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_task_actions(db: AsyncSession, task_id: str) -> list[AgentAction]:
    """Get all actions for a task, ordered by sequence."""
    result = await db.execute(
        select(AgentAction).where(AgentAction.task_id == task_id).order_by(AgentAction.sequence)
    )
    return list(result.scalars().all())


async def get_task_by_id(db: AsyncSession, task_id: str) -> AgentTask | None:
    """Get a single task by ID."""
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    return result.scalar_one_or_none()


async def spawn_from_channel(
    db: AsyncSession,
    *,
    user_id: str,
    instruction: str,
    platform: str,
    chat_id: str | None = None,
    message_id: str | None = None,
) -> AgentTask:
    """Convenience wrapper for spawning an agent from a messaging channel webhook."""
    return await create_agent_task(
        db,
        user_id=user_id,
        instruction=instruction,
        platform=platform,
        platform_chat_id=chat_id,
        platform_message_id=message_id,
        agent_type="coder",
    )
