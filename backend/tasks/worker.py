"""Background worker that processes queued tasks."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from backend.database import _session_factory
from backend.tasks.service import TaskQueueService


class BackgroundWorker:
    """Async background worker that processes queued tasks."""

    def __init__(self, max_concurrent: int = 3, poll_interval: float = 5.0) -> None:
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            try:
                if not _session_factory:
                    await asyncio.sleep(self.poll_interval)
                    continue
                async with _session_factory() as db:
                    active = await TaskQueueService.get_active_count(db)
                    if active >= self.max_concurrent:
                        await asyncio.sleep(self.poll_interval)
                        continue
                    task = await TaskQueueService.get_next_runnable(db)
                    if not task:
                        await asyncio.sleep(self.poll_interval)
                        continue
                    await TaskQueueService.mark_running(db, task.id)
                asyncio.create_task(self._execute_task(task.id, task.task_type, task.payload_json, task.user_id))
            except Exception:
                await asyncio.sleep(self.poll_interval)

    async def _execute_task(self, task_id: str, task_type: str, payload_json: str, user_id: str) -> None:
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
                if _session_factory:
                    async with _session_factory() as db:
                        await TaskQueueService.mark_failed(db, task_id, str(exc))


async def _handle_plan_execution(task_id: str, user_id: str, payload: dict) -> dict:
    from backend.planner.agent_runner import AgentRunner

    plan_id = payload.get("plan_id")
    if not plan_id:
        raise ValueError("plan_id is required")

    async def on_progress(data: dict) -> None:
        if _session_factory and data.get("type") in ("step_completed", "step_failed"):
            async with _session_factory() as db:
                total = data.get("total_steps", 1)
                completed = data.get("completed", 0)
                pct = int((completed / total) * 100) if total else 0
                await TaskQueueService.update_progress(db, task_id, pct, data.get("title", ""))

    runner = AgentRunner(plan_id=plan_id, user_id=user_id, on_step_update=on_progress)
    return await runner.run()


async def _handle_research(task_id: str, user_id: str, payload: dict) -> dict:
    from backend.research.service import ResearchService
    from config import settings

    topic = payload.get("topic")
    if not topic:
        raise ValueError("topic is required")
    provider = payload.get("provider", "google")
    model = payload.get("model")
    api_key = settings.GEMINI_API_KEY if provider == "google" else getattr(settings, "OPENAI_API_KEY", "")
    if not _session_factory:
        raise ValueError("Database not initialized")
    async with _session_factory() as db:
        async def on_progress(data: dict) -> None:
            phase_pct = {"planning": 10, "searching": 40, "synthesizing": 80, "completed": 100}
            await TaskQueueService.update_progress(db, task_id, phase_pct.get(data.get("phase", ""), 50), data.get("phase", ""))

        return await ResearchService.start_research(
            db,
            user_id,
            topic,
            api_key,
            provider_name=provider,
            model=model,
            conversation_id=payload.get("conversation_id"),
            on_progress=on_progress,
        )


async def _handle_custom(task_id: str, user_id: str, payload: dict) -> dict:
    return {"status": "completed", "task_id": task_id, "payload": payload}


TASK_HANDLERS: dict[str, Any] = {
    "plan_execution": _handle_plan_execution,
    "research": _handle_research,
    "custom": _handle_custom,
}
