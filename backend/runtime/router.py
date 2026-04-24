"""Runtime API endpoints shared by the web app and channel surfaces."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from auth import _verify_session
from backend import database
from backend.runtime.agent_loop import DEFAULT_INSTRUCTIONS
from backend.runtime.context_window import build_prepared_context
from backend.runtime.persistence import RuntimeRun
from backend.runtime.tools.native import get_enabled_native_tools

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


def _current_user_uid(request: Request) -> str:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    uid = str(payload.get("uid") or "").strip()
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid session")
    return uid


def _session_ctx() -> Any:
    factory = getattr(database, "_session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="Database session factory is not initialised")
    return factory()


async def _resolve_session_owner(session_id: str) -> str | None:
    async with _session_ctx() as db:
        stmt = (
            select(RuntimeRun.owner_uid)
            .where(RuntimeRun.session_id == session_id)
            .order_by(RuntimeRun.started_at.desc())
            .limit(1)
        )
        value = (await db.execute(stmt)).scalar_one_or_none()
        return str(value) if value else None


def _native_tool_names() -> list[str]:
    names: list[str] = []
    for tool in get_enabled_native_tools():
        name = getattr(tool, "name", None)
        if isinstance(name, str) and name:
            names.append(name)
    return names


@router.get("/context-meter/{session_id}")
async def context_meter(session_id: str, request: Request) -> dict[str, Any]:
    """Return the projected loaded context footprint for a session.

    The response mirrors the `context_meter` runtime event emitted before
    every model run. It intentionally accounts for the same buckets the
    dispatch loop loads: system prompt, active tools, checkpoints,
    workspace/memory placeholders, pending tool outputs, recent history,
    and the current user message placeholder.
    """
    user_uid = _current_user_uid(request)
    owner_uid = await _resolve_session_owner(session_id)
    if owner_uid is not None and owner_uid != user_uid:
        raise HTTPException(status_code=404, detail="Session not found")
    effective_owner = owner_uid or user_uid
    prepared = await build_prepared_context(
        session_factory=_session_ctx,
        session_id=session_id,
        owner_uid=effective_owner,
        current_text="",
        instructions=DEFAULT_INSTRUCTIONS,
        tool_names=_native_tool_names(),
    )
    return prepared.meter


__all__ = ["router"]
