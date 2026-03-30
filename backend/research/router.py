"""API routes for deep research sessions."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import _session_factory, get_session
from backend.key_management import KeyManager
from backend.research.service import ResearchService
from config import settings

research_router = APIRouter(prefix="/api/research", tags=["research"])
key_manager = KeyManager(settings.ENCRYPTION_SECRET)


def _get_user_uid(request: Request) -> str:
    payload = _verify_session(request.cookies.get("aegis_session"))
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload["uid"]


@research_router.post("/start")
async def start_research(payload: dict[str, Any], request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    topic = str(payload.get("topic", "")).strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    provider_name = payload.get("provider", "google")
    api_key = await key_manager.get_key(db, uid, provider_name)
    if not api_key:
        api_key = {"google": settings.GEMINI_API_KEY, "openai": settings.OPENAI_API_KEY, "anthropic": settings.ANTHROPIC_API_KEY}.get(provider_name, "")
    if not api_key:
        raise HTTPException(status_code=400, detail=f"No API key for {provider_name}")

    async def run_research() -> None:
        if _session_factory is None:
            return
        async with _session_factory() as bg_db:
            await ResearchService.start_research(
                bg_db,
                uid,
                topic,
                api_key,
                provider_name=provider_name,
                model=payload.get("model"),
                conversation_id=payload.get("conversation_id"),
            )

    asyncio.create_task(run_research())
    return {"ok": True, "message": "Research started"}


@research_router.get("/")
async def list_research_sessions(request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    sessions = await ResearchService.list_sessions(db, uid)
    return {"ok": True, "sessions": sessions}


@research_router.get("/{research_id}")
async def get_research_session(research_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    session_data = await ResearchService.get_session(db, research_id, uid)
    if not session_data:
        raise HTTPException(status_code=404, detail="Research session not found")
    return {"ok": True, "session": session_data}
