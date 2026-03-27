"""Sub-agent execution engine.

Runs an approved TaskPlan by executing steps according to their dependency graph.
Independent steps run in parallel. Each step uses the assigned provider/model.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import TaskPlan, _session_factory
from backend.key_management import KeyManager
from backend.planner.service import PlannerService
from backend.providers import get_provider
from backend.providers.base import ChatMessage
from config import settings

logger = logging.getLogger(__name__)

key_manager = KeyManager(settings.ENCRYPTION_SECRET)
StepCallback = Callable[[dict[str, Any]], Awaitable[None]]


class DependencyGraph:
    """Build and query a step dependency graph."""

    def __init__(self, steps: list[dict[str, Any]]) -> None:
        self.steps = {str(step["id"]): step for step in steps}
        self.dependents: dict[str, list[str]] = {}
        for step in steps:
            for dep_id in step.get("depends_on", []):
                dep_key = str(dep_id)
                self.dependents.setdefault(dep_key, []).append(str(step["id"]))

    def get_ready_steps(self, completed: set[str], running: set[str], failed: set[str]) -> list[str]:
        """Return step IDs whose dependencies are all completed and aren't already resolved."""
        ready: list[str] = []
        for step_id, step in self.steps.items():
            if step_id in completed or step_id in running or step_id in failed:
                continue
            deps = [str(dep) for dep in step.get("depends_on", [])]
            if all(dep in completed for dep in deps):
                ready.append(step_id)
        return ready

    def has_blocked_path(self, failed: set[str]) -> set[str]:
        """Return step IDs that can never complete because a dependency failed."""
        blocked: set[str] = set()
        changed = True
        while changed:
            changed = False
            for step_id, step in self.steps.items():
                if step_id in blocked or step_id in failed:
                    continue
                deps = [str(dep) for dep in step.get("depends_on", [])]
                if any(dep in failed or dep in blocked for dep in deps):
                    blocked.add(step_id)
                    changed = True
        return blocked


class AgentRunner:
    """Execute a task plan by running sub-agents per step."""

    def __init__(
        self,
        plan_id: str,
        user_id: str,
        on_step_update: StepCallback | None = None,
        max_concurrent: int = 5,
    ) -> None:
        self.plan_id = plan_id
        self.user_id = user_id
        self.on_step_update = on_step_update
        self.max_concurrent = max_concurrent
        self._cancel_event = asyncio.Event()
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self) -> dict[str, Any]:
        """Execute the full plan and return final status."""
        if not _session_factory:
            return {"status": "failed", "error": "Database not initialized"}

        async with _session_factory() as db:
            plan_data = await PlannerService.get_plan(db, self.plan_id, self.user_id)
            if not plan_data:
                return {"status": "failed", "error": "Plan not found"}
            if plan_data["status"] not in ("approved", "running"):
                return {"status": "failed", "error": f"Plan status is {plan_data['status']}, expected approved"}

            plan_obj = await db.get(TaskPlan, self.plan_id)
            if plan_obj:
                plan_obj.status = "running"
                plan_obj.started_at = datetime.now(timezone.utc)
                await db.commit()

        steps = list(plan_data["steps"])
        graph = DependencyGraph(steps)
        completed: set[str] = set()
        running: set[str] = set()
        failed: set[str] = set()
        tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
        skipped: set[str] = set()

        await self._notify({"type": "plan_started", "plan_id": self.plan_id, "total_steps": len(steps)})

        while True:
            if self._cancel_event.is_set():
                for task in tasks.values():
                    task.cancel()
                await self._update_plan_status("cancelled")
                await self._notify({"type": "plan_cancelled", "plan_id": self.plan_id, "status": "cancelled"})
                return {"status": "cancelled"}

            blocked = graph.has_blocked_path(failed)
            all_done = completed | failed | blocked
            if len(all_done) >= len(steps):
                final_status = "completed" if not failed else "failed"
                await self._update_plan_status(final_status)
                await self._notify({"type": "plan_completed", "plan_id": self.plan_id, "status": final_status})
                return {
                    "status": final_status,
                    "completed": len(completed),
                    "failed": len(failed),
                    "blocked": len(blocked),
                }

            for step_id in blocked:
                if step_id in skipped or step_id in failed:
                    continue
                skipped.add(step_id)
                await self._update_step_db(step_id, "skipped")
                await self._notify({"type": "step_skipped", "step_id": step_id, "reason": "dependency failed"})

            ready = graph.get_ready_steps(completed, running, failed | blocked)
            for step_id in ready:
                if len(running) >= self.max_concurrent:
                    break
                step_data = graph.steps[step_id]
                running.add(step_id)
                tasks[step_id] = asyncio.create_task(self._execute_step(step_data))

            if tasks:
                done, _ = await asyncio.wait(
                    tasks.values(),
                    timeout=1.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    finished_id: str | None = None
                    for step_id, runner_task in tasks.items():
                        if runner_task is task:
                            finished_id = step_id
                            break
                    if not finished_id:
                        continue
                    del tasks[finished_id]
                    running.discard(finished_id)
                    try:
                        result = task.result()
                        if result.get("success"):
                            completed.add(finished_id)
                        else:
                            failed.add(finished_id)
                    except Exception:  # noqa: BLE001
                        failed.add(finished_id)
            else:
                await asyncio.sleep(0.5)

    async def _execute_step(self, step: dict[str, Any]) -> dict[str, Any]:
        """Execute a single step using assigned provider/model."""
        step_id = str(step["id"])
        provider_name = str(step.get("assigned_provider", "google"))
        model = step.get("assigned_model")

        await self._update_step_db(step_id, "running")
        await self._notify(
            {
                "type": "step_started",
                "step_id": step_id,
                "title": step["title"],
                "provider": provider_name,
                "model": model,
            }
        )

        async with self._semaphore:
            try:
                api_key = await self._get_api_key(provider_name)
                if not api_key:
                    raise ValueError(f"No API key for provider {provider_name}")

                provider = get_provider(provider_name, api_key)
                step_prompt = self._build_step_prompt(step)

                messages = [
                    ChatMessage(
                        role="system",
                        content="You are a focused task executor. Complete the assigned task thoroughly and return the result.",
                    ),
                    ChatMessage(role="user", content=step_prompt),
                ]

                response = await provider.chat(messages, model=model, temperature=0.5, max_tokens=4096)
                tokens_used = int(response.usage.get("total_tokens", 0))
                await self._update_step_db(
                    step_id,
                    "completed",
                    result_text=response.content,
                    tokens_used=tokens_used,
                )
                await self._notify(
                    {
                        "type": "step_completed",
                        "step_id": step_id,
                        "title": step["title"],
                        "result_preview": response.content[:200],
                        "tokens_used": tokens_used,
                    }
                )
                return {"success": True, "content": response.content}
            except Exception as exc:  # noqa: BLE001
                error_msg = str(exc)
                logger.exception("Step %s failed: %s", step_id, error_msg)
                await self._update_step_db(step_id, "failed", error_message=error_msg)
                await self._notify(
                    {
                        "type": "step_failed",
                        "step_id": step_id,
                        "title": step["title"],
                        "error": error_msg,
                    }
                )
                return {"success": False, "error": error_msg}

    def _build_step_prompt(self, step: dict[str, Any]) -> str:
        """Build execution prompt for a step."""
        parts = [f"Task: {step['title']}"]
        if step.get("description"):
            parts.append(f"\nDetails: {step['description']}")
        return "\n".join(parts)

    async def _get_api_key(self, provider_name: str) -> str | None:
        """Get API key from BYOK or platform fallback."""
        if not _session_factory:
            return None
        async with _session_factory() as db:
            key = await key_manager.get_key(db, self.user_id, provider_name)
            if key:
                return key
        fallback = {
            "google": settings.GEMINI_API_KEY,
            "openai": getattr(settings, "OPENAI_API_KEY", ""),
            "anthropic": getattr(settings, "ANTHROPIC_API_KEY", ""),
            "mistral": getattr(settings, "MISTRAL_API_KEY", ""),
            "groq": getattr(settings, "GROQ_API_KEY", ""),
        }
        return fallback.get(provider_name, "")

    async def _update_step_db(
        self,
        step_id: str,
        status: str,
        result_text: str | None = None,
        error_message: str | None = None,
        tokens_used: int = 0,
    ) -> None:
        """Update step status in DB safely."""
        if not _session_factory:
            return
        try:
            async with _session_factory() as db:
                await PlannerService.update_step_status(
                    db,
                    step_id,
                    status,
                    result_text=result_text,
                    error_message=error_message,
                    tokens_used=tokens_used,
                )
        except Exception:  # noqa: BLE001
            logger.debug("Failed to update step %s status", step_id, exc_info=True)

    async def _update_plan_status(self, status: str) -> None:
        """Update plan status in DB."""
        if not _session_factory:
            return
        try:
            async with _session_factory() as db:
                plan = await db.get(TaskPlan, self.plan_id)
                if plan:
                    plan.status = status
                    if status in ("completed", "failed", "cancelled"):
                        plan.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:  # noqa: BLE001
            logger.debug("Failed to update plan %s status", self.plan_id, exc_info=True)

    async def _notify(self, data: dict[str, Any]) -> None:
        """Send progress update via callback."""
        if self.on_step_update:
            try:
                await self.on_step_update(data)
            except Exception:  # noqa: BLE001
                logger.debug("Step update notification failed", exc_info=True)

    def cancel(self) -> None:
        """Signal cancellation."""
        self._cancel_event.set()
