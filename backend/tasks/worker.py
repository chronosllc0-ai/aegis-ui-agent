"""Background worker that continuously executes queued tasks."""

from __future__ import annotations

import asyncio
from typing import Any

from backend.database import _session_factory
from backend.tasks.service import TaskQueueService


async def _handle_plan_execution(payload: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(1)
    return {"status": "completed", "type": "plan_execution", "payload": payload}


async def _handle_research(payload: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(1)
    return {"status": "completed", "type": "research", "payload": payload}


async def _handle_custom(payload: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(1)
    prompt = str(payload.get("prompt", "")).strip()
    return {"status": "completed", "prompt": prompt, "message": "Custom task processing not yet implemented"}


TASK_HANDLERS: dict[str, Any] = {
    "plan_execution": _handle_plan_execution,
    "research": _handle_research,
    "custom": _handle_custom,
}


class BackgroundWorker:
    """In-process task worker with DB-backed queue."""

    def __init__(self, max_concurrent: int = 3, poll_interval: float = 2.0) -> None:
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval
        self._loop_task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def start(self) -> None:
        if self._loop_task and not self._loop_task.done():
            return
        self._stopped.clear()
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stopped.set()
        if self._loop_task and not self._loop_task.done():
            await self._loop_task

    async def _run_loop(self) -> None:
        while not self._stopped.is_set():
            if _session_factory is None:
                await asyncio.sleep(self.poll_interval)
                continue
            async with _session_factory() as session:
                task = await TaskQueueService.get_next_runnable(session)
                if not task:
                    await asyncio.sleep(self.poll_interval)
                    continue
                await TaskQueueService.mark_running(session, task.id)
                asyncio.create_task(self._execute_task(task.id, task.task_type, task.payload_json))
            await asyncio.sleep(0.1)

    async def _execute_task(self, task_id: str, task_type: str, payload_json: str) -> None:
        async with self._semaphore:
            if _session_factory is None:
                return
            import json

            payload = json.loads(payload_json) if payload_json else {}
            handler = TASK_HANDLERS.get(task_type, _handle_custom)
            try:
                result = await handler(payload)
                async with _session_factory() as session:
                    await TaskQueueService.mark_completed(session, task_id, result)
            except Exception as exc:
                async with _session_factory() as session:
                    await TaskQueueService.mark_failed(session, task_id, str(exc))
