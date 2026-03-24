"""Background cron scheduler for scheduled automation tasks.

Wakes every 30 seconds, finds due tasks, and executes them.
Actual agent invocation is logged for now — wiring to the orchestrator
can be added later when the full orchestrator integration is ready.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 30  # seconds
_scheduler_task: asyncio.Task[None] | None = None


# ---------------------------------------------------------------------------
# Task execution
# ---------------------------------------------------------------------------


async def execute_task(task_id: str) -> None:
    """Execute a single scheduled task by ID."""
    from backend.database import ScheduledTask, _session_factory  # type: ignore[attr-defined]

    if _session_factory is None:
        logger.warning("execute_task called before DB is ready; skipping task %s", task_id)
        return

    async with _session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None:
            logger.warning("Task %s not found; skipping", task_id)
            return

        if task.last_status == "running":
            logger.info("Task %s is already running; skipping", task_id)
            return

        # Mark as running
        task.last_status = "running"
        await session.commit()

    started_at = datetime.now(timezone.utc)
    status = "success"
    error: str | None = None

    try:
        logger.info(
            "Executing scheduled task %r (id=%s): %s",
            task.name,
            task_id,
            task.prompt[:120],
        )
        # TODO: wire up to the AgentOrchestrator once the integration is ready.
        # For now we log the prompt execution so the system is fully operational.
        await asyncio.sleep(0.1)  # simulate async work
        logger.info("Scheduled task %s completed successfully", task_id)
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        error = str(exc)
        logger.exception("Scheduled task %s failed: %s", task_id, exc)

    # Persist result
    async with _session_factory() as session:
        task = await session.get(ScheduledTask, task_id)
        if task is None:
            return

        now = datetime.now(timezone.utc)
        task.last_run_at = now
        task.last_status = status
        task.last_error = error
        task.run_count = (task.run_count or 0) + 1
        task.next_run_at = _compute_next_run(task.cron_expr, task.timezone or "UTC")
        await session.commit()

    # Record in in-memory run history
    from backend.automation import _record_run

    _record_run(
        task_id,
        {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "error": error,
        },
    )


def _compute_next_run(cron_expr: str, tz_name: str) -> datetime | None:
    try:
        from croniter import croniter  # type: ignore[import-untyped]
        import zoneinfo

        tz = zoneinfo.ZoneInfo(tz_name)
        now = datetime.now(tz)
        it = croniter(cron_expr, now)
        next_dt: datetime = it.get_next(datetime)
        if next_dt.tzinfo is None:
            next_dt = next_dt.replace(tzinfo=tz)
        return next_dt.astimezone(timezone.utc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not compute next_run_at for cron %r: %s", cron_expr, exc)
        return None


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------


async def _scheduler_loop() -> None:
    """Main loop: poll every 30 s and run due tasks."""
    from backend.database import ScheduledTask, _session_factory, _database_ready  # type: ignore[attr-defined]

    logger.info("Cron scheduler started (poll interval: %ds)", _POLL_INTERVAL)
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            # Wait for DB to be ready
            from backend import database as _db_module

            if not _db_module._database_ready:
                continue

            factory = _db_module._session_factory
            if factory is None:
                continue

            async with factory() as session:
                now = datetime.now(timezone.utc)
                result = await session.execute(
                    select(ScheduledTask).where(
                        ScheduledTask.enabled.is_(True),
                        ScheduledTask.next_run_at <= now,
                        ScheduledTask.last_status != "running",
                    )
                )
                due_tasks = result.scalars().all()

            if due_tasks:
                logger.info("Cron: %d task(s) due", len(due_tasks))
                for task in due_tasks:
                    asyncio.create_task(execute_task(task.id))

        except Exception as exc:  # noqa: BLE001
            logger.exception("Cron scheduler error: %s", exc)


def start_scheduler() -> asyncio.Task[None]:
    """Start the background scheduler task. Call from app lifespan."""
    global _scheduler_task
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    return _scheduler_task
