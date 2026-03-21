# Codex Phase 8: Sub-Agent Orchestration & Parallel Execution

## Project Context
Aegis is a FastAPI + React/TypeScript app. Phase 7 added the `backend/planner/` module which decomposes user prompts into structured task plans with steps. Now we need an agent runner that actually *executes* those plans — spawning sub-agents per step, running independent steps in parallel, routing each to the best model, and streaming real-time progress to the frontend.

The multi-model provider system exists at `backend/providers/` with adapters for OpenAI, Anthropic, Google, Mistral, and Groq. The BYOK key management is at `backend/key_management.py`.

## What to implement
Create a sub-agent execution engine that takes an approved TaskPlan, builds a dependency graph, runs independent steps concurrently, streams per-step progress over WebSocket, and marks steps/plan as complete.

## CRITICAL RULES
- Do NOT modify: `orchestrator.py`, `session.py`, `navigator.py`, `analyzer.py`, `executor.py`, `mcp_client.py`
- Do NOT modify: any existing file in `backend/providers/`, `backend/connectors/`, `backend/admin/`
- Do NOT modify: `backend/credit_rates.py`, `backend/credit_service.py`, `backend/key_management.py`, `backend/conversation_service.py`
- Do NOT modify: `backend/planner/service.py` (only add to `backend/planner/`)
- Do NOT modify: `frontend/src/components/settings/`, `frontend/src/components/LandingPage.tsx`, `frontend/src/components/AuthPage.tsx`, `frontend/src/components/TaskPlanView.tsx`
- Do NOT modify: `auth.py`
- The agent runner must be resilient: if one step fails, other independent steps continue. The plan is marked `failed` only when a step with dependents fails and no path to completion exists.
- All step execution is fire-and-forget safe — a crash in one step must NOT crash the runner or WebSocket
- Use the provider system (`backend/providers/get_provider`) for all LLM calls
- ESLint strict rules apply to all frontend files

---

## 1. Create `backend/planner/agent_runner.py`

```python
"""Sub-agent execution engine.

Runs an approved TaskPlan by executing steps according to their dependency graph.
Independent steps run in parallel. Each step uses the assigned provider/model.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import TaskPlan, TaskStep, _session_factory
from backend.key_management import KeyManager
from backend.planner.service import PlannerService
from backend.providers import get_provider
from backend.providers.base import ChatMessage
from config import settings

logger = logging.getLogger(__name__)

key_manager = KeyManager(settings.ENCRYPTION_SECRET)

# Type for the WebSocket callback
StepCallback = Callable[[dict[str, Any]], Awaitable[None]]


class DependencyGraph:
    """Builds and queries a step dependency graph."""

    def __init__(self, steps: list[dict]) -> None:
        self.steps = {s["id"]: s for s in steps}
        self.dependents: dict[str, list[str]] = {}  # step_id -> list of steps that depend on it
        for step in steps:
            for dep_id in step.get("depends_on", []):
                self.dependents.setdefault(dep_id, []).append(step["id"])

    def get_ready_steps(self, completed: set[str], running: set[str], failed: set[str]) -> list[str]:
        """Return step IDs whose dependencies are all completed and aren't running/done/failed."""
        ready = []
        for step_id, step in self.steps.items():
            if step_id in completed or step_id in running or step_id in failed:
                continue
            deps = step.get("depends_on", [])
            if all(d in completed for d in deps):
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
                deps = step.get("depends_on", [])
                if any(d in failed or d in blocked for d in deps):
                    blocked.add(step_id)
                    changed = True
        return blocked


class AgentRunner:
    """Executes a task plan by running sub-agents per step."""

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
        """Execute the full plan. Returns final plan status."""
        if not _session_factory:
            return {"status": "failed", "error": "Database not initialized"}

        async with _session_factory() as db:
            plan_data = await PlannerService.get_plan(db, self.plan_id, self.user_id)
            if not plan_data:
                return {"status": "failed", "error": "Plan not found"}
            if plan_data["status"] not in ("approved", "running"):
                return {"status": "failed", "error": f"Plan status is {plan_data['status']}, expected approved"}

            # Mark plan as running
            plan_obj = await db.get(TaskPlan, self.plan_id)
            if plan_obj:
                plan_obj.status = "running"
                plan_obj.started_at = datetime.now(timezone.utc)
                await db.commit()

        steps = plan_data["steps"]
        graph = DependencyGraph(steps)

        completed: set[str] = set()
        running: set[str] = set()
        failed: set[str] = set()
        tasks: dict[str, asyncio.Task] = {}

        await self._notify({"type": "plan_started", "plan_id": self.plan_id, "total_steps": len(steps)})

        while True:
            if self._cancel_event.is_set():
                for task in tasks.values():
                    task.cancel()
                await self._update_plan_status("cancelled")
                return {"status": "cancelled"}

            # Check for blocked steps
            blocked = graph.has_blocked_path(failed)
            all_done = completed | failed | blocked
            if len(all_done) >= len(steps):
                # All steps resolved
                final_status = "completed" if not failed else "failed"
                await self._update_plan_status(final_status)
                await self._notify({"type": "plan_completed", "plan_id": self.plan_id, "status": final_status})
                return {"status": final_status, "completed": len(completed), "failed": len(failed), "blocked": len(blocked)}

            # Mark blocked steps as skipped
            for step_id in blocked:
                if step_id not in failed:
                    await self._update_step_db(step_id, "skipped")
                    await self._notify({"type": "step_skipped", "step_id": step_id, "reason": "dependency failed"})

            # Find and launch ready steps
            ready = graph.get_ready_steps(completed, running, failed | blocked)
            for step_id in ready:
                if len(running) >= self.max_concurrent:
                    break
                step_data = graph.steps[step_id]
                running.add(step_id)
                tasks[step_id] = asyncio.create_task(self._execute_step(step_data))

            # Wait for any task to complete
            if tasks:
                done, _ = await asyncio.wait(
                    tasks.values(),
                    timeout=1.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    # Find which step this task belongs to
                    finished_id = None
                    for sid, t in tasks.items():
                        if t is task:
                            finished_id = sid
                            break
                    if finished_id:
                        del tasks[finished_id]
                        running.discard(finished_id)
                        try:
                            result = task.result()
                            if result.get("success"):
                                completed.add(finished_id)
                            else:
                                failed.add(finished_id)
                        except Exception:
                            failed.add(finished_id)
            else:
                await asyncio.sleep(0.5)

    async def _execute_step(self, step: dict) -> dict[str, Any]:
        """Execute a single step using the assigned provider/model."""
        step_id = step["id"]
        provider_name = step.get("assigned_provider", "google")
        model = step.get("assigned_model")

        await self._update_step_db(step_id, "running")
        await self._notify({"type": "step_started", "step_id": step_id, "title": step["title"], "provider": provider_name, "model": model})

        async with self._semaphore:
            try:
                # Get API key
                api_key = await self._get_api_key(provider_name)
                if not api_key:
                    raise ValueError(f"No API key for provider {provider_name}")

                provider = get_provider(provider_name, api_key)

                # Build the step prompt
                step_prompt = self._build_step_prompt(step)

                messages = [
                    ChatMessage(role="system", content="You are a focused task executor. Complete the assigned task thoroughly and return the result."),
                    ChatMessage(role="user", content=step_prompt),
                ]

                response = await provider.chat(messages, model=model, temperature=0.5, max_tokens=4096)

                tokens = response.usage.get("total_tokens", 0)
                await self._update_step_db(
                    step_id, "completed",
                    result_text=response.content,
                    tokens_used=tokens,
                )
                await self._notify({
                    "type": "step_completed",
                    "step_id": step_id,
                    "title": step["title"],
                    "result_preview": response.content[:200],
                    "tokens_used": tokens,
                })
                return {"success": True, "content": response.content}

            except Exception as exc:
                error_msg = str(exc)
                logger.exception("Step %s failed: %s", step_id, error_msg)
                await self._update_step_db(step_id, "failed", error_message=error_msg)
                await self._notify({
                    "type": "step_failed",
                    "step_id": step_id,
                    "title": step["title"],
                    "error": error_msg,
                })
                return {"success": False, "error": error_msg}

    def _build_step_prompt(self, step: dict) -> str:
        """Build the execution prompt for a step."""
        parts = [f"Task: {step['title']}"]
        if step.get("description"):
            parts.append(f"\nDetails: {step['description']}")
        # In future phases, inject results from dependency steps here
        return "\n".join(parts)

    async def _get_api_key(self, provider_name: str) -> str | None:
        """Get API key — user's BYOK key or platform fallback."""
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
        """Update step status in database (fire-and-forget safe)."""
        if not _session_factory:
            return
        try:
            async with _session_factory() as db:
                await PlannerService.update_step_status(
                    db, step_id, status,
                    result_text=result_text,
                    error_message=error_message,
                    tokens_used=tokens_used,
                )
        except Exception:
            logger.debug("Failed to update step %s status", step_id, exc_info=True)

    async def _update_plan_status(self, status: str) -> None:
        """Update plan status in database."""
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
        except Exception:
            logger.debug("Failed to update plan %s status", self.plan_id, exc_info=True)

    async def _notify(self, data: dict[str, Any]) -> None:
        """Send progress update via callback."""
        if self.on_step_update:
            try:
                await self.on_step_update(data)
            except Exception:
                logger.debug("Step update notification failed", exc_info=True)

    def cancel(self) -> None:
        """Signal cancellation."""
        self._cancel_event.set()
```

## 2. Create `backend/planner/executor_routes.py`

```python
"""API routes for plan execution."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import get_session
from backend.planner.agent_runner import AgentRunner
from backend.planner.service import PlannerService

logger = logging.getLogger(__name__)
executor_router = APIRouter(prefix="/api/plans", tags=["plan-execution"])

# Track running plans per user
_active_runners: dict[str, AgentRunner] = {}


def _get_user_uid(request) -> str:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload["uid"]


@executor_router.post("/{plan_id}/execute")
async def execute_plan(
    plan_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start executing an approved plan. Returns immediately.

    Connect to the WebSocket at /ws/plan/{plan_id} to stream progress.
    """
    uid = _get_user_uid(request)
    plan = await PlannerService.get_plan(db, plan_id, uid)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan["status"] not in ("approved",):
        raise HTTPException(status_code=400, detail=f"Plan status is {plan['status']}, must be approved")

    runner_key = f"{uid}:{plan_id}"
    if runner_key in _active_runners:
        raise HTTPException(status_code=409, detail="Plan is already running")

    runner = AgentRunner(plan_id=plan_id, user_id=uid)
    _active_runners[runner_key] = runner

    async def run_and_cleanup():
        try:
            await runner.run()
        finally:
            _active_runners.pop(runner_key, None)

    asyncio.create_task(run_and_cleanup())

    return {"ok": True, "message": "Plan execution started", "ws_url": f"/ws/plan/{plan_id}"}


@executor_router.post("/{plan_id}/stop")
async def stop_plan(
    plan_id: str,
    request: Any,
) -> dict[str, Any]:
    """Cancel a running plan."""
    uid = _get_user_uid(request)
    runner_key = f"{uid}:{plan_id}"
    runner = _active_runners.get(runner_key)
    if not runner:
        raise HTTPException(status_code=404, detail="No active runner for this plan")
    runner.cancel()
    return {"ok": True, "message": "Cancellation requested"}


@executor_router.websocket("/ws/plan/{plan_id}")
async def plan_progress_ws(websocket: WebSocket, plan_id: str) -> None:
    """WebSocket for streaming plan execution progress.

    Client connects after calling POST /api/plans/{plan_id}/execute.
    Receives JSON messages with step-by-step updates.
    """
    await websocket.accept()

    # Extract user from cookie
    token = websocket.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        await websocket.close(code=4001, reason="Not authenticated")
        return

    uid = payload["uid"]
    runner_key = f"{uid}:{plan_id}"
    runner = _active_runners.get(runner_key)

    if not runner:
        await websocket.send_json({"type": "error", "message": "No active runner. Start execution first."})
        await websocket.close()
        return

    # Attach WebSocket callback to the runner
    message_queue: asyncio.Queue[dict] = asyncio.Queue()

    async def on_update(data: dict) -> None:
        await message_queue.put(data)

    runner.on_step_update = on_update

    try:
        while True:
            try:
                msg = await asyncio.wait_for(message_queue.get(), timeout=30.0)
                await websocket.send_json(msg)
                if msg.get("type") in ("plan_completed", "plan_cancelled"):
                    break
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        logger.debug("Plan progress WS disconnected for %s", plan_id)
    except Exception:
        logger.debug("Plan progress WS error", exc_info=True)
    finally:
        if runner.on_step_update is on_update:
            runner.on_step_update = None
```

## 3. Register executor routes in `main.py`

Add import (with other backend imports):
```python
from backend.planner.executor_routes import executor_router
```

Add router registration:
```python
app.include_router(executor_router)
```

## 4. Create `frontend/src/components/AgentActivityFeed.tsx`

A live feed component that shows what each sub-agent is doing in real-time. Connects to the plan progress WebSocket.

```tsx
import { useCallback, useEffect, useRef, useState } from 'react'

type FeedEvent = {
  type: string
  step_id?: string
  title?: string
  provider?: string
  model?: string
  result_preview?: string
  tokens_used?: number
  error?: string
  reason?: string
  status?: string
  total_steps?: number
  timestamp: number
}

type AgentActivityFeedProps = {
  planId: string
  wsBaseUrl?: string
}

const EVENT_ICONS: Record<string, { icon: string; color: string }> = {
  plan_started: { icon: '▶', color: 'text-blue-400' },
  step_started: { icon: '◉', color: 'text-blue-400' },
  step_completed: { icon: '✓', color: 'text-emerald-400' },
  step_failed: { icon: '✗', color: 'text-red-400' },
  step_skipped: { icon: '—', color: 'text-zinc-500' },
  plan_completed: { icon: '■', color: 'text-emerald-400' },
  plan_cancelled: { icon: '■', color: 'text-amber-400' },
  heartbeat: { icon: '·', color: 'text-zinc-700' },
}

export function AgentActivityFeed({ planId, wsBaseUrl }: AgentActivityFeedProps) {
  const [events, setEvents] = useState<FeedEvent[]>([])
  const [connected, setConnected] = useState(false)
  const feedRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const addEvent = useCallback((evt: FeedEvent) => {
    if (evt.type === 'heartbeat') return
    setEvents((prev) => [...prev, evt])
  }, [])

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const base = wsBaseUrl || `${protocol}//${window.location.host}`
    const ws = new WebSocket(`${base}/ws/plan/${planId}`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        addEvent({ ...data, timestamp: Date.now() })
      } catch { /* ignore parse errors */ }
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [planId, wsBaseUrl, addEvent])

  // Auto-scroll to bottom
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight
    }
  }, [events])

  return (
    <div className="rounded-xl border border-[#2a2a2a] bg-[#1a1a1a]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#2a2a2a] px-4 py-2.5">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Agent Activity</h4>
        <div className="flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
          <span className="text-[10px] text-zinc-500">{connected ? 'Live' : 'Disconnected'}</span>
        </div>
      </div>

      {/* Feed */}
      <div ref={feedRef} className="max-h-[400px] overflow-y-auto p-3">
        {events.length === 0 ? (
          <p className="py-4 text-center text-xs text-zinc-600">Waiting for events...</p>
        ) : (
          <div className="space-y-1">
            {events.map((evt, i) => {
              const style = EVENT_ICONS[evt.type] || EVENT_ICONS.heartbeat
              return (
                <div key={`${evt.type}-${evt.step_id || ''}-${i}`} className="flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-zinc-800/50">
                  <span className={`mt-0.5 text-xs font-mono ${style.color}`}>{style.icon}</span>
                  <div className="min-w-0 flex-1">
                    <span className="text-xs text-zinc-300">
                      {evt.title || evt.type.replace(/_/g, ' ')}
                    </span>
                    {evt.provider && (
                      <span className="ml-2 rounded bg-zinc-700 px-1 py-0.5 text-[9px] text-zinc-500">
                        {evt.provider}{evt.model ? `/${evt.model}` : ''}
                      </span>
                    )}
                    {evt.result_preview && (
                      <p className="mt-0.5 text-[11px] text-zinc-500 line-clamp-2">{evt.result_preview}</p>
                    )}
                    {evt.error && (
                      <p className="mt-0.5 text-[11px] text-red-400">{evt.error}</p>
                    )}
                    {evt.tokens_used ? (
                      <span className="text-[9px] text-zinc-600">{evt.tokens_used.toLocaleString()} tokens</span>
                    ) : null}
                  </div>
                  <span className="shrink-0 text-[9px] text-zinc-700">
                    {new Date(evt.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
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

## 5. Create `frontend/src/hooks/usePlanExecution.ts`

```typescript
import { useCallback, useState } from 'react'
import { apiUrl } from '../lib/api'

type PlanExecutionState = {
  executing: boolean
  error: string | null
}

export function usePlanExecution() {
  const [state, setState] = useState<PlanExecutionState>({ executing: false, error: null })

  const executePlan = useCallback(async (planId: string): Promise<boolean> => {
    setState({ executing: true, error: null })
    try {
      const resp = await fetch(apiUrl(`/api/plans/${planId}/execute`), {
        method: 'POST',
        credentials: 'include',
      })
      const data = await resp.json()
      if (!data.ok) {
        setState({ executing: false, error: data.detail || 'Execution failed' })
        return false
      }
      setState({ executing: false, error: null })
      return true
    } catch (err) {
      setState({ executing: false, error: err instanceof Error ? err.message : 'Execution failed' })
      return false
    }
  }, [])

  const stopPlan = useCallback(async (planId: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/plans/${planId}/stop`), {
        method: 'POST',
        credentials: 'include',
      })
      const data = await resp.json()
      return Boolean(data.ok)
    } catch {
      return false
    }
  }, [])

  return { ...state, executePlan, stopPlan }
}
```

---

## Verification
1. `cd frontend && npm run build` — zero errors
2. `cd frontend && npm run lint` — zero errors
3. Backend starts without import errors
4. `POST /api/plans/{id}/execute` starts a runner and returns ws_url
5. `POST /api/plans/{id}/stop` cancels a running plan
6. WebSocket at `/ws/plan/{id}` streams step events
7. AgentActivityFeed renders live events with auto-scroll
8. Independent steps run in parallel (verify with a plan with 3+ independent tasks)
9. Failed step correctly blocks dependent steps (marked as skipped)
10. Plan status transitions: approved → running → completed/failed/cancelled
