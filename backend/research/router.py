"""API routes for deep research."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import get_session
from backend.research.service import ResearchService
from config import settings

research_router = APIRouter(prefix="/api/research", tags=["research"])


def _get_user_uid(request: Request) -> str:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload["uid"]


@research_router.post("/")
async def start_research(payload: dict[str, Any], request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    topic = str(payload.get("topic", "")).strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")
    provider = str(payload.get("provider", "google"))
    api_key = ""
    if provider == "google":
        api_key = settings.GEMINI_API_KEY
    elif provider == "openai":
        api_key = getattr(settings, "OPENAI_API_KEY", "")
    elif provider == "anthropic":
        api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=400, detail=f"No API key configured for provider '{provider}'")
    result = await ResearchService.start_research(
        db,
        uid,
        topic,
        api_key,
        provider_name=provider,
        model=payload.get("model"),
        conversation_id=payload.get("conversation_id"),
    )
    return {"ok": True, "session": result}


@research_router.get("/")
async def list_research(
    request: Request,
    db: AsyncSession = Depends(get_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    uid = _get_user_uid(request)
    sessions = await ResearchService.list_sessions(db, uid, limit=limit, offset=offset)
    return {"ok": True, "sessions": sessions}


@research_router.get("/{research_id}")
async def get_research(research_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    session_data = await ResearchService.get_session(db, uid, research_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Research session not found")
    return {"ok": True, "session": session_data}
