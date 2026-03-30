"""API routes for memory management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import get_session
from backend.key_management import KeyManager
from backend.memory.service import MemoryService
from config import settings

memory_router = APIRouter(prefix="/api/memory", tags=["memory"])
key_manager = KeyManager(settings.ENCRYPTION_SECRET)


def _get_user_uid(request: Request) -> str:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload["uid"]


async def _get_user_embedding_key(db: AsyncSession, uid: str) -> tuple[str | None, str]:
    key = await key_manager.get_key(db, uid, "openai")
    if key:
        return key, "openai"
    if settings.OPENAI_API_KEY:
        return settings.OPENAI_API_KEY, "openai"
    return None, "hash"


@memory_router.get("/")
async def list_memories(
    request: Request,
    db: AsyncSession = Depends(get_session),
    category: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    uid = _get_user_uid(request)
    memories = await MemoryService.list_memories(db, uid, category=category, limit=limit, offset=offset)
    return {"ok": True, "memories": memories}


@memory_router.post("/")
async def create_memory(payload: dict[str, Any], request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    content = str(payload.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    api_key, provider = await _get_user_embedding_key(db, uid)
    memory = await MemoryService.store(
        db,
        uid,
        content,
        category=str(payload.get("category", "general")),
        source="manual",
        importance=float(payload.get("importance", 0.5)),
        api_key=api_key,
        embedding_provider=provider,
    )
    return {"ok": True, "memory": memory}


@memory_router.get("/search")
async def search_memories(
    request: Request,
    db: AsyncSession = Depends(get_session),
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    category: str | None = Query(None),
) -> dict[str, Any]:
    uid = _get_user_uid(request)
    api_key, provider = await _get_user_embedding_key(db, uid)
    memories = await MemoryService.recall(
        db,
        uid,
        q,
        limit=limit,
        category=category,
        api_key=api_key,
        embedding_provider=provider,
    )
    return {"ok": True, "memories": memories}


@memory_router.get("/stats")
async def memory_stats(request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    return {"ok": True, "stats": await MemoryService.get_stats(db, uid)}


@memory_router.get("/{memory_id}")
async def get_memory(memory_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    memory = await MemoryService.get_memory(db, memory_id, uid)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": memory}


@memory_router.put("/{memory_id}")
async def update_memory(
    memory_id: str,
    payload: dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    uid = _get_user_uid(request)
    api_key, provider = await _get_user_embedding_key(db, uid)
    memory = await MemoryService.update_memory(
        db,
        memory_id,
        uid,
        content=payload.get("content"),
        category=payload.get("category"),
        importance=payload.get("importance"),
        is_pinned=payload.get("is_pinned"),
        api_key=api_key,
        embedding_provider=provider,
    )
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": memory}


@memory_router.delete("/{memory_id}")
async def delete_memory(memory_id: str, request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    uid = _get_user_uid(request)
    ok = await MemoryService.delete_memory(db, memory_id, uid)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}
