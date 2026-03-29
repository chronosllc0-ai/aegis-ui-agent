"""API routes for task planning."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import get_session
from backend.key_management import KeyManager
from backend.planner.service import PlannerService
from config import settings

logger = logging.getLogger(__name__)
planner_router = APIRouter(prefix="/api/plans", tags=["plans"])
key_manager = KeyManager(settings.ENCRYPTION_SECRET)


def _get_user_uid(request: Request) -> str:
    """Extract authenticated user UID from request cookies."""
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return str(payload["uid"])


@planner_router.post("/decompose")
async def decompose_prompt_endpoint(
    payload: dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Decompose a prompt into a task plan."""
    uid = _get_user_uid(request)
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    provider_name = str(payload.get("provider", "google")).strip() or "google"
    model = str(payload.get("model", "")).strip() or None
    conversation_id = str(payload.get("conversation_id", "")).strip() or None

    api_key = await key_manager.get_key(db, uid, provider_name)
    if not api_key:
        fallback_keys = {
            "google": settings.GEMINI_API_KEY,
            "openai": getattr(settings, "OPENAI_API_KEY", ""),
            "anthropic": getattr(settings, "ANTHROPIC_API_KEY", ""),
            "xai": getattr(settings, "XAI_API_KEY", ""),
            "openrouter": getattr(settings, "OPENROUTER_API_KEY", ""),
        }
        api_key = fallback_keys.get(provider_name, "")
    if not api_key:
        raise HTTPException(status_code=400, detail=f"No API key available for {provider_name}")

    try:
        plan_data = await PlannerService.decompose(prompt, api_key, provider_name, model)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Decomposition failed")
        raise HTTPException(status_code=500, detail=f"Decomposition failed: {exc}") from exc

    plan = await PlannerService.create_plan(
        db,
        uid,
        prompt,
        plan_data,
        provider_name,
        model or "default",
        conversation_id=conversation_id,
    )
    full_plan = await PlannerService.get_plan(db, plan.id, uid)
    return {"ok": True, "plan": full_plan}


@planner_router.get("/")
async def list_plans_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List user's task plans."""
    uid = _get_user_uid(request)
    plans = await PlannerService.list_plans(db, uid, limit, offset)
    return {"ok": True, "plans": plans}


@planner_router.get("/{plan_id}")
async def get_plan_endpoint(
    plan_id: str,
    request: Request,
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
    request: Request,
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
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Cancel a plan."""
    uid = _get_user_uid(request)
    ok = await PlannerService.cancel_plan(db, plan_id, uid)
    if not ok:
        raise HTTPException(status_code=400, detail="Plan not found or already completed")
    return {"ok": True}
