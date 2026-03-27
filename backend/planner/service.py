"""Task decomposition service.

Takes a user prompt and uses an LLM to break it into structured subtasks.
"""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import TaskPlan, TaskStep
from backend.providers import get_provider
from backend.providers.base import ChatMessage

logger = logging.getLogger(__name__)

DECOMPOSITION_SYSTEM_PROMPT = """You are a task planning engine. Given a user's request, decompose it into a structured plan of actionable subtasks.

Rules:
- Each task should be a concrete, executable action
- Include dependencies between tasks (which tasks must complete before others can start)
- Assign a recommended model type for each task: "reasoning" (complex analysis), "coding" (code generation), "fast" (quick responses), "research" (web search, data gathering), "creative" (writing, design)
- If the request is simple (1-2 steps), still return a plan but with fewer tasks
- Maximum 15 subtasks for any single plan
- Each task must have a clear, measurable completion criteria

Respond with ONLY valid JSON in this exact format:
{
  "title": "Short plan title",
  "tasks": [
    {
      "id": "task_1",
      "title": "Short task title",
      "description": "Detailed description of what to do",
      "task_type": "reasoning|coding|fast|research|creative",
      "depends_on": [],
      "subtasks": [
        {
          "id": "task_1_1",
          "title": "Subtask title",
          "description": "Subtask details",
          "task_type": "fast",
          "depends_on": ["task_1"]
        }
      ]
    }
  ]
}"""

TASK_TYPE_TO_PROVIDER: dict[str, tuple[str, str]] = {
    "reasoning": ("anthropic", "claude-sonnet-4-20250514"),
    "coding": ("anthropic", "claude-sonnet-4-20250514"),
    "fast": ("google", "gemini-2.5-flash"),
    "research": ("google", "gemini-2.5-pro"),
    "creative": ("openai", "gpt-5.2"),
}


class PlannerService:
    """Manages task plan lifecycle."""

    @staticmethod
    async def decompose(
        prompt: str,
        api_key: str,
        provider_name: str = "google",
        model: str | None = None,
    ) -> dict:
        """Decompose a prompt into a structured task plan using an LLM."""
        provider = get_provider(provider_name, api_key)
        resolved_model = model or (provider.available_models[0] if provider.available_models else None)

        messages = [
            ChatMessage(role="system", content=DECOMPOSITION_SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt),
        ]

        response = await provider.chat(messages, model=resolved_model, temperature=0.3, max_tokens=4096)
        content = response.content.strip()

        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3].strip()

        return json.loads(content)

    @staticmethod
    async def create_plan(
        session: AsyncSession,
        user_id: str,
        prompt: str,
        plan_data: dict,
        provider: str,
        model: str,
        conversation_id: str | None = None,
    ) -> TaskPlan:
        """Persist a decomposed plan and its steps to the database."""
        plan_id = str(uuid4())

        plan = TaskPlan(
            id=plan_id,
            user_id=user_id,
            conversation_id=conversation_id,
            original_prompt=prompt,
            title=plan_data.get("title", prompt[:200]),
            status="draft",
            provider=provider,
            model=model,
            plan_json=json.dumps(plan_data),
        )
        session.add(plan)

        step_index = 0
        tasks = plan_data.get("tasks", [])
        for task in tasks:
            task_type = task.get("task_type", "reasoning")
            rec_provider, rec_model = TASK_TYPE_TO_PROVIDER.get(task_type, ("google", "gemini-2.5-pro"))
            task_id = task.get("id", str(uuid4()))

            step = TaskStep(
                id=task_id,
                plan_id=plan_id,
                step_index=step_index,
                title=task.get("title", f"Step {step_index + 1}"),
                description=task.get("description", ""),
                assigned_provider=rec_provider,
                assigned_model=rec_model,
                depends_on=json.dumps(task.get("depends_on", [])),
            )
            session.add(step)
            step_index += 1

            for subtask in task.get("subtasks", []):
                sub_type = subtask.get("task_type", "fast")
                sub_provider, sub_model = TASK_TYPE_TO_PROVIDER.get(sub_type, ("google", "gemini-2.5-flash"))

                sub_step = TaskStep(
                    id=subtask.get("id", str(uuid4())),
                    plan_id=plan_id,
                    parent_step_id=task_id,
                    step_index=step_index,
                    title=subtask.get("title", f"Step {step_index + 1}"),
                    description=subtask.get("description", ""),
                    assigned_provider=sub_provider,
                    assigned_model=sub_model,
                    depends_on=json.dumps(subtask.get("depends_on", [task_id])),
                )
                session.add(sub_step)
                step_index += 1

        await session.commit()
        await session.refresh(plan)
        return plan

    @staticmethod
    async def get_plan(session: AsyncSession, plan_id: str, user_id: str) -> dict | None:
        """Fetch a plan with all its steps."""
        result = await session.execute(select(TaskPlan).where(TaskPlan.id == plan_id, TaskPlan.user_id == user_id))
        plan = result.scalar_one_or_none()
        if not plan:
            return None

        steps_result = await session.execute(select(TaskStep).where(TaskStep.plan_id == plan_id).order_by(TaskStep.step_index))
        steps = steps_result.scalars().all()

        return {
            "id": plan.id,
            "title": plan.title,
            "status": plan.status,
            "original_prompt": plan.original_prompt,
            "provider": plan.provider,
            "model": plan.model,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            "started_at": plan.started_at.isoformat() if plan.started_at else None,
            "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
            "steps": [
                {
                    "id": s.id,
                    "parent_step_id": s.parent_step_id,
                    "step_index": s.step_index,
                    "title": s.title,
                    "description": s.description,
                    "status": s.status,
                    "assigned_provider": s.assigned_provider,
                    "assigned_model": s.assigned_model,
                    "depends_on": json.loads(s.depends_on) if s.depends_on else [],
                    "result_text": s.result_text,
                    "error_message": s.error_message,
                    "tokens_used": s.tokens_used,
                    "credits_used": s.credits_used,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
                for s in steps
            ],
        }

    @staticmethod
    async def list_plans(session: AsyncSession, user_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
        """List plans for a user with basic info."""
        result = await session.execute(
            select(TaskPlan).where(TaskPlan.user_id == user_id).order_by(TaskPlan.created_at.desc()).limit(limit).offset(offset)
        )
        plans = result.scalars().all()
        return [
            {
                "id": p.id,
                "title": p.title,
                "status": p.status,
                "original_prompt": p.original_prompt[:200],
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in plans
        ]

    @staticmethod
    async def approve_plan(session: AsyncSession, plan_id: str, user_id: str) -> bool:
        """Mark a draft plan as approved (ready for execution)."""
        result = await session.execute(
            update(TaskPlan).where(TaskPlan.id == plan_id, TaskPlan.user_id == user_id, TaskPlan.status == "draft").values(status="approved")
        )
        await session.commit()
        return bool(result.rowcount and result.rowcount > 0)

    @staticmethod
    async def cancel_plan(session: AsyncSession, plan_id: str, user_id: str) -> bool:
        """Cancel a plan."""
        result = await session.execute(
            update(TaskPlan)
            .where(TaskPlan.id == plan_id, TaskPlan.user_id == user_id, TaskPlan.status.in_(["draft", "approved", "running"]))
            .values(status="cancelled")
        )
        await session.commit()
        return bool(result.rowcount and result.rowcount > 0)

    @staticmethod
    async def update_step_status(
        session: AsyncSession,
        step_id: str,
        status: str,
        result_text: str | None = None,
        error_message: str | None = None,
        tokens_used: int = 0,
        credits_used: float = 0.0,
    ) -> bool:
        """Update the status and result of a single step."""
        from datetime import datetime, timezone

        values: dict[str, object] = {"status": status}
        if status == "running":
            values["started_at"] = datetime.now(timezone.utc)
        if status in ("completed", "failed"):
            values["completed_at"] = datetime.now(timezone.utc)
        if result_text is not None:
            values["result_text"] = result_text
        if error_message is not None:
            values["error_message"] = error_message
        if tokens_used:
            values["tokens_used"] = tokens_used
        if credits_used:
            values["credits_used"] = credits_used

        result = await session.execute(update(TaskStep).where(TaskStep.id == step_id).values(**values))
        await session.commit()
        return bool(result.rowcount and result.rowcount > 0)


async def decompose_prompt(
    prompt: str,
    api_key: str,
    provider_name: str = "google",
    model: str | None = None,
) -> dict:
    """Convenience wrapper for PlannerService.decompose."""
    return await PlannerService.decompose(prompt, api_key, provider_name, model)
