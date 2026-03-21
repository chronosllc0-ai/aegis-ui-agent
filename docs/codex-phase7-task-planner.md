# Codex Phase 7: Task Decomposition & Planning Engine

## Project Context
Aegis is a FastAPI + React/TypeScript app. Backend at repo root. Frontend at `frontend/`. Database: SQLAlchemy async (PostgreSQL/SQLite). The orchestrator in `orchestrator.py` currently processes user instructions as single flat tasks using Google ADK. There is no decomposition — a complex prompt runs as one monolithic action. This phase adds a planner that breaks complex prompts into visual task plans before execution.

## What to implement
Create a task decomposition engine that takes a user prompt, uses an LLM to break it into structured subtasks with dependencies, and exposes API endpoints for plan CRUD. Also create the frontend `TaskPlanView` component that renders the plan with checkboxes and real-time status.

## CRITICAL RULES
- Do NOT modify: `orchestrator.py`, `session.py`, `navigator.py`, `analyzer.py`, `executor.py`, `mcp_client.py`
- Do NOT modify: any file in `backend/providers/`, `backend/connectors/`, `backend/admin/`, `backend/credit_rates.py`, `backend/credit_service.py`, `backend/key_management.py`, `backend/conversation_service.py`
- Do NOT modify: `frontend/src/components/settings/`, `frontend/src/components/LandingPage.tsx`, `frontend/src/components/AuthPage.tsx`
- Do NOT modify: `auth.py`, `config.py` (except adding new env vars to the Settings class)
- Use `apiUrl('/path')` from `frontend/src/lib/api.ts` for ALL frontend API calls
- The planner uses the multi-model provider system (`backend/providers/`) — NOT the google-genai client directly
- ESLint is strict: NO `setState` in `useEffect` bodies, NO ref access during render
- Use `*bold*` not `**bold**` in any UI text
- Frontend uses Tailwind v4. Dark theme: `bg-[#111]`, `bg-[#1a1a1a]`, `border-[#2a2a2a]`, `text-zinc-*`

## Database models

Add to `backend/database.py` (AFTER the existing `SupportMessage` class):

```python
class TaskPlan(Base):
    """A decomposed task plan from a user prompt."""

    __tablename__ = "task_plans"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    conversation_id = Column(String(255), ForeignKey("conversations.id"), nullable=True)
    original_prompt = Column(Text, nullable=False)
    title = Column(String(500), nullable=False)
    status = Column(String(20), default="draft")  # draft | approved | running | completed | failed | cancelled
    provider = Column(String(50))       # which provider was used to decompose
    model = Column(String(100))         # which model was used to decompose
    plan_json = Column(Text, nullable=False)  # JSON: list of TaskStep dicts
    result_summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))


class TaskStep(Base):
    """Individual step within a task plan."""

    __tablename__ = "task_steps"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    plan_id = Column(String(255), ForeignKey("task_plans.id"), nullable=False, index=True)
    parent_step_id = Column(String(255), ForeignKey("task_steps.id"), nullable=True)
    step_index = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    status = Column(String(20), default="pending")  # pending | running | completed | failed | skipped
    assigned_provider = Column(String(50))
    assigned_model = Column(String(100))
    depends_on = Column(Text)  # JSON array of step IDs this depends on
    result_text = Column(Text)
    error_message = Column(Text)
    tokens_used = Column(Integer, default=0)
    credits_used = Column(Float, default=0.0)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

---

## 1. Create `backend/planner/__init__.py`

```python
"""Task decomposition and planning engine."""

from .service import PlannerService, decompose_prompt

__all__ = ["PlannerService", "decompose_prompt"]
```

## 2. Create `backend/planner/service.py`

```python
"""Task decomposition service.

Takes a user prompt and uses an LLM to break it into structured subtasks.
"""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

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

# Map task types to recommended providers
TASK_TYPE_TO_PROVIDER: dict[str, tuple[str, str]] = {
    "reasoning": ("anthropic", "claude-sonnet-4-20250514"),
    "coding": ("anthropic", "claude-sonnet-4-20250514"),
    "fast": ("groq", "llama-3.3-70b-versatile"),
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
        """Decompose a prompt into a structured task plan using an LLM.

        Returns the parsed plan dict.
        """
        provider = get_provider(provider_name, api_key)
        model = model or provider.available_models[0] if provider.available_models else None

        messages = [
            ChatMessage(role="system", content=DECOMPOSITION_SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt),
        ]

        response = await provider.chat(messages, model=model, temperature=0.3, max_tokens=4096)
        content = response.content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3].strip()

        plan = json.loads(content)
        return plan

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

            step = TaskStep(
                id=task.get("id", str(uuid4())),
                plan_id=plan_id,
                step_index=step_index,
                title=task["title"],
                description=task.get("description", ""),
                assigned_provider=rec_provider,
                assigned_model=rec_model,
                depends_on=json.dumps(task.get("depends_on", [])),
            )
            session.add(step)
            step_index += 1

            for subtask in task.get("subtasks", []):
                sub_type = subtask.get("task_type", "fast")
                sub_provider, sub_model = TASK_TYPE_TO_PROVIDER.get(sub_type, ("groq", "llama-3.3-70b-versatile"))

                sub_step = TaskStep(
                    id=subtask.get("id", str(uuid4())),
                    plan_id=plan_id,
                    parent_step_id=task.get("id"),
                    step_index=step_index,
                    title=subtask["title"],
                    description=subtask.get("description", ""),
                    assigned_provider=sub_provider,
                    assigned_model=sub_model,
                    depends_on=json.dumps(subtask.get("depends_on", [])),
                )
                session.add(sub_step)
                step_index += 1

        await session.commit()
        await session.refresh(plan)
        return plan

    @staticmethod
    async def get_plan(session: AsyncSession, plan_id: str, user_id: str) -> dict | None:
        """Fetch a plan with all its steps."""
        result = await session.execute(
            select(TaskPlan).where(TaskPlan.id == plan_id, TaskPlan.user_id == user_id)
        )
        plan = result.scalar_one_or_none()
        if not plan:
            return None

        steps_result = await session.execute(
            select(TaskStep).where(TaskStep.plan_id == plan_id).order_by(TaskStep.step_index)
        )
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
            select(TaskPlan)
            .where(TaskPlan.user_id == user_id)
            .order_by(TaskPlan.created_at.desc())
            .limit(limit)
            .offset(offset)
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
            update(TaskPlan)
            .where(TaskPlan.id == plan_id, TaskPlan.user_id == user_id, TaskPlan.status == "draft")
            .values(status="approved")
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def cancel_plan(session: AsyncSession, plan_id: str, user_id: str) -> bool:
        """Cancel a plan."""
        result = await session.execute(
            update(TaskPlan)
            .where(TaskPlan.id == plan_id, TaskPlan.user_id == user_id, TaskPlan.status.in_(["draft", "approved", "running"]))
            .values(status="cancelled")
        )
        await session.commit()
        return result.rowcount > 0

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

        values: dict = {"status": status}
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

        result = await session.execute(
            update(TaskStep).where(TaskStep.id == step_id).values(**values)
        )
        await session.commit()
        return result.rowcount > 0


async def decompose_prompt(
    prompt: str,
    api_key: str,
    provider_name: str = "google",
    model: str | None = None,
) -> dict:
    """Convenience wrapper for PlannerService.decompose."""
    return await PlannerService.decompose(prompt, api_key, provider_name, model)
```

## 3. Create `backend/planner/router.py`

```python
"""API routes for task planning."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import get_session
from backend.key_management import KeyManager
from backend.planner.service import PlannerService
from config import settings

logger = logging.getLogger(__name__)
planner_router = APIRouter(prefix="/api/plans", tags=["plans"])
key_manager = KeyManager(settings.ENCRYPTION_SECRET)


def _get_user_uid(request) -> str:
    """Extract authenticated user UID from request cookies."""
    from fastapi import Request
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload["uid"]


@planner_router.post("/decompose")
async def decompose_prompt_endpoint(
    payload: dict[str, Any],
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Decompose a prompt into a task plan.

    Body: { "prompt": "...", "provider": "google", "model": "gemini-2.5-pro" }
    """
    uid = _get_user_uid(request)
    prompt = payload.get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    provider_name = payload.get("provider", "google")
    model = payload.get("model")

    # Get user's API key for the provider
    api_key = await key_manager.get_key(db, uid, provider_name)
    if not api_key:
        # Fall back to platform key
        fallback_keys = {
            "google": settings.GEMINI_API_KEY,
            "openai": getattr(settings, "OPENAI_API_KEY", ""),
            "anthropic": getattr(settings, "ANTHROPIC_API_KEY", ""),
        }
        api_key = fallback_keys.get(provider_name, "")
    if not api_key:
        raise HTTPException(status_code=400, detail=f"No API key available for {provider_name}")

    try:
        plan_data = await PlannerService.decompose(prompt, api_key, provider_name, model)
    except Exception as exc:
        logger.exception("Decomposition failed")
        raise HTTPException(status_code=500, detail=f"Decomposition failed: {exc}") from exc

    plan = await PlannerService.create_plan(
        db, uid, prompt, plan_data, provider_name, model or "default",
    )
    full_plan = await PlannerService.get_plan(db, plan.id, uid)
    return {"ok": True, "plan": full_plan}


@planner_router.get("/")
async def list_plans_endpoint(
    request: Any,
    db: AsyncSession = Depends(get_session),
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """List user's task plans."""
    uid = _get_user_uid(request)
    plans = await PlannerService.list_plans(db, uid, limit, offset)
    return {"ok": True, "plans": plans}


@planner_router.get("/{plan_id}")
async def get_plan_endpoint(
    plan_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a specific plan with all steps."""
    uid = _get_user_uid(request)
    plan = await PlannerService.get_plan(db, plan_id, uid)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"ok": True, "plan": plan}


@planner_router.post("/{plan_id}/approve")
async def approve_plan_endpoint(
    plan_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Approve a draft plan for execution."""
    uid = _get_user_uid(request)
    ok = await PlannerService.approve_plan(db, plan_id, uid)
    if not ok:
        raise HTTPException(status_code=400, detail="Plan not found or not in draft status")
    return {"ok": True}


@planner_router.post("/{plan_id}/cancel")
async def cancel_plan_endpoint(
    plan_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Cancel a plan."""
    uid = _get_user_uid(request)
    ok = await PlannerService.cancel_plan(db, plan_id, uid)
    if not ok:
        raise HTTPException(status_code=400, detail="Plan not found or already completed")
    return {"ok": True}
```

## 4. Register router in `main.py`

Add import (with the other backend imports near the top):
```python
from backend.planner.router import planner_router
```

Add router registration (next to the other `app.include_router` calls):
```python
app.include_router(planner_router)
```

## 5. Create `frontend/src/components/TaskPlanView.tsx`

This component renders a task plan with:
- Plan title and status badge
- Nested checklist of tasks and subtasks
- Real-time status indicators per step (pending ○, running ◉ with pulse, completed ✓, failed ✗)
- Provider/model badge on each step
- "Approve & Execute" button for draft plans
- "Cancel" button for running/draft plans
- Collapsible step details (click to expand description + result)

```tsx
import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../lib/api'

type TaskStep = {
  id: string
  parent_step_id: string | null
  step_index: number
  title: string
  description: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  assigned_provider: string
  assigned_model: string
  depends_on: string[]
  result_text: string | null
  error_message: string | null
  tokens_used: number
  credits_used: number
  started_at: string | null
  completed_at: string | null
}

type Plan = {
  id: string
  title: string
  status: 'draft' | 'approved' | 'running' | 'completed' | 'failed' | 'cancelled'
  original_prompt: string
  provider: string
  model: string
  steps: TaskStep[]
  created_at: string | null
  started_at: string | null
  completed_at: string | null
}

type TaskPlanViewProps = {
  planId: string
  onClose?: () => void
}

const STATUS_STYLES: Record<string, { icon: string; color: string; bg: string }> = {
  pending: { icon: '○', color: 'text-zinc-500', bg: 'bg-zinc-800' },
  running: { icon: '◉', color: 'text-blue-400', bg: 'bg-blue-900/30' },
  completed: { icon: '✓', color: 'text-emerald-400', bg: 'bg-emerald-900/30' },
  failed: { icon: '✗', color: 'text-red-400', bg: 'bg-red-900/30' },
  skipped: { icon: '—', color: 'text-zinc-600', bg: 'bg-zinc-800/50' },
}

const PLAN_STATUS_COLORS: Record<string, string> = {
  draft: 'bg-zinc-700 text-zinc-300',
  approved: 'bg-blue-900/50 text-blue-300',
  running: 'bg-blue-600 text-white',
  completed: 'bg-emerald-900/50 text-emerald-300',
  failed: 'bg-red-900/50 text-red-300',
  cancelled: 'bg-zinc-800 text-zinc-500',
}

export function TaskPlanView({ planId, onClose }: TaskPlanViewProps) {
  const [plan, setPlan] = useState<Plan | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set())
  const [actionBusy, setActionBusy] = useState(false)

  const fetchPlan = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl(`/api/plans/${planId}`), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setPlan(data.plan)
      else setError(data.detail || 'Failed to load plan')
    } catch {
      setError('Failed to load plan')
    } finally {
      setLoading(false)
    }
  }, [planId])

  useEffect(() => {
    fetchPlan()
  }, [fetchPlan])

  // Poll for updates when plan is running
  useEffect(() => {
    if (!plan || plan.status !== 'running') return
    const interval = setInterval(fetchPlan, 3000)
    return () => clearInterval(interval)
  }, [plan, fetchPlan])

  const toggleStep = (stepId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev)
      if (next.has(stepId)) next.delete(stepId)
      else next.add(stepId)
      return next
    })
  }

  const handleApprove = async () => {
    if (!plan) return
    setActionBusy(true)
    try {
      const resp = await fetch(apiUrl(`/api/plans/${plan.id}/approve`), { method: 'POST', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) await fetchPlan()
      else setError(data.detail || 'Failed to approve')
    } catch {
      setError('Failed to approve plan')
    } finally {
      setActionBusy(false)
    }
  }

  const handleCancel = async () => {
    if (!plan) return
    setActionBusy(true)
    try {
      const resp = await fetch(apiUrl(`/api/plans/${plan.id}/cancel`), { method: 'POST', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) await fetchPlan()
      else setError(data.detail || 'Failed to cancel')
    } catch {
      setError('Failed to cancel plan')
    } finally {
      setActionBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
      </div>
    )
  }

  if (error || !plan) {
    return (
      <div className="rounded-lg border border-red-800/50 bg-red-900/20 p-4 text-sm text-red-300">
        {error || 'Plan not found'}
      </div>
    )
  }

  // Separate root tasks from subtasks
  const rootSteps = plan.steps.filter((s) => !s.parent_step_id)
  const childSteps = (parentId: string) => plan.steps.filter((s) => s.parent_step_id === parentId)

  const completedCount = plan.steps.filter((s) => s.status === 'completed').length
  const totalCount = plan.steps.length

  return (
    <div className="rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-4">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-white">{plan.title}</h3>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${PLAN_STATUS_COLORS[plan.status] || ''}`}>
              {plan.status}
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-500">{plan.original_prompt}</p>
          {/* Progress bar */}
          <div className="mt-2 flex items-center gap-2">
            <div className="h-1.5 flex-1 rounded-full bg-zinc-800">
              <div
                className="h-1.5 rounded-full bg-blue-500 transition-all"
                style={{ width: `${totalCount > 0 ? (completedCount / totalCount) * 100 : 0}%` }}
              />
            </div>
            <span className="text-[11px] text-zinc-500">{completedCount}/{totalCount}</span>
          </div>
        </div>
        {onClose && (
          <button type="button" onClick={onClose} className="ml-2 text-zinc-500 hover:text-zinc-300">✕</button>
        )}
      </div>

      {/* Steps */}
      <div className="space-y-1.5">
        {rootSteps.map((step) => {
          const ss = STATUS_STYLES[step.status] || STATUS_STYLES.pending
          const expanded = expandedSteps.has(step.id)
          const children = childSteps(step.id)

          return (
            <div key={step.id}>
              <button
                type="button"
                onClick={() => toggleStep(step.id)}
                className={`flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left transition-colors ${ss.bg} hover:bg-zinc-800`}
              >
                <span className={`mt-0.5 text-sm font-mono ${ss.color} ${step.status === 'running' ? 'animate-pulse' : ''}`}>
                  {ss.icon}
                </span>
                <div className="min-w-0 flex-1">
                  <span className="text-sm text-zinc-200">{step.title}</span>
                  <div className="mt-0.5 flex items-center gap-2">
                    <span className="rounded bg-zinc-700 px-1.5 py-0.5 text-[9px] text-zinc-400">
                      {step.assigned_provider}/{step.assigned_model}
                    </span>
                    {step.depends_on.length > 0 && (
                      <span className="text-[9px] text-zinc-600">depends on: {step.depends_on.join(', ')}</span>
                    )}
                  </div>
                </div>
                <span className="text-[10px] text-zinc-600">{expanded ? '▾' : '▸'}</span>
              </button>

              {expanded && (
                <div className="ml-8 mt-1 space-y-1">
                  {step.description && (
                    <p className="text-xs text-zinc-400">{step.description}</p>
                  )}
                  {step.result_text && (
                    <div className="rounded-lg bg-zinc-800/50 p-2 text-xs text-zinc-300">
                      {step.result_text}
                    </div>
                  )}
                  {step.error_message && (
                    <div className="rounded-lg bg-red-900/20 p-2 text-xs text-red-300">
                      {step.error_message}
                    </div>
                  )}
                  {children.map((child) => {
                    const cs = STATUS_STYLES[child.status] || STATUS_STYLES.pending
                    return (
                      <div key={child.id} className={`flex items-start gap-2 rounded-lg px-2 py-1.5 ${cs.bg}`}>
                        <span className={`text-xs font-mono ${cs.color} ${child.status === 'running' ? 'animate-pulse' : ''}`}>
                          {cs.icon}
                        </span>
                        <div className="min-w-0 flex-1">
                          <span className="text-xs text-zinc-300">{child.title}</span>
                          <span className="ml-2 rounded bg-zinc-700 px-1 py-0.5 text-[8px] text-zinc-500">
                            {child.assigned_provider}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Actions */}
      <div className="mt-4 flex gap-2">
        {plan.status === 'draft' && (
          <button
            type="button"
            onClick={handleApprove}
            disabled={actionBusy}
            className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {actionBusy ? 'Approving...' : 'Approve & Execute'}
          </button>
        )}
        {['draft', 'approved', 'running'].includes(plan.status) && (
          <button
            type="button"
            onClick={handleCancel}
            disabled={actionBusy}
            className="rounded-lg border border-zinc-700 px-4 py-2 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
          >
            Cancel
          </button>
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
4. `POST /api/plans/decompose` returns a structured plan
5. `GET /api/plans/` lists user plans
6. `GET /api/plans/{id}` returns full plan with steps
7. `POST /api/plans/{id}/approve` changes status
8. `POST /api/plans/{id}/cancel` changes status
9. TaskPlanView renders with proper status icons and expand/collapse
10. No modifications to orchestrator.py or any other restricted files
