"""API routes for plan execution."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import get_session
from backend.planner.agent_runner import AgentRunner
from backend.planner.service import PlannerService

logger = logging.getLogger(__name__)
executor_router = APIRouter(prefix="/api/plans", tags=["plan-execution"])

_active_runners: dict[str, AgentRunner] = {}


def _get_user_uid(request: Request) -> str:
    """Return authenticated user UID from aegis_session cookie."""
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return str(payload["uid"])


@executor_router.post("/{plan_id}/execute")
async def execute_plan(
    plan_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start executing an approved plan. Returns immediately."""
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

    async def run_and_cleanup() -> None:
        try:
            await runner.run()
        finally:
            _active_runners.pop(runner_key, None)

    asyncio.create_task(run_and_cleanup())
    return {"ok": True, "message": "Plan execution started", "ws_url": f"/ws/plan/{plan_id}"}


@executor_router.post("/{plan_id}/stop")
async def stop_plan(plan_id: str, request: Request) -> dict[str, Any]:
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
    """WebSocket endpoint streaming plan execution progress."""
    await websocket.accept()

    token = websocket.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        await websocket.close(code=4001, reason="Not authenticated")
        return

    uid = str(payload["uid"])
    runner_key = f"{uid}:{plan_id}"
    runner = _active_runners.get(runner_key)

    if not runner:
        await websocket.send_json({"type": "error", "message": "No active runner. Start execution first."})
        await websocket.close()
        return

    message_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def on_update(data: dict[str, Any]) -> None:
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
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        logger.debug("Plan progress WS disconnected for %s", plan_id)
    except Exception:  # noqa: BLE001
        logger.debug("Plan progress WS error", exc_info=True)
    finally:
        if runner.on_step_update is on_update:
            runner.on_step_update = None
