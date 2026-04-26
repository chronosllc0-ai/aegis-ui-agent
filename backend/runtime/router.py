"""Runtime API endpoints shared by the web app and channel surfaces."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from auth import _verify_session
from backend import database
from backend.runtime.agent_loop import DEFAULT_INSTRUCTIONS
from backend.runtime.context_window import build_prepared_context
from backend.runtime.integration import get_registry
from backend.runtime.persistence import RuntimeRun
from backend.runtime.tools.connectors import load_connector_tools
from backend.runtime.tools.native import get_enabled_native_tools

logger = logging.getLogger(__name__)

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


def _tool_name(tool: Any) -> str:
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) else ""


async def _existing_mcp_tool_names(owner_uid: str) -> list[str]:
    """Return MCP tool names from this user's *existing* supervisor only.

    The context-meter endpoint must never spin up an MCP provider just
    to answer a GET — that would leak resources for users who have
    never triggered a real run. We peek at the supervisor that
    dispatch already created (if any) and read its cached provider.
    """
    registry = get_registry()
    if registry is None:
        return []
    supervisor = registry._supervisors.get(owner_uid)  # type: ignore[attr-defined]
    if supervisor is None:
        return []
    provider = getattr(supervisor, "_mcp_provider", None)
    if provider is None:
        return []
    try:
        tools = list(await provider.get_tools())
    except Exception:  # noqa: BLE001
        logger.exception("context-meter: MCP provider tool listing failed owner=%s", owner_uid)
        return []
    return [name for name in (_tool_name(t) for t in tools) if name]


async def _connector_tool_names(owner_uid: str) -> list[str]:
    try:
        tools = list(await load_connector_tools(owner_uid))
    except Exception:  # noqa: BLE001
        logger.exception("context-meter: connector loader failed owner=%s", owner_uid)
        return []
    return [name for name in (_tool_name(t) for t in tools) if name]


async def _effective_tool_names(owner_uid: str) -> list[str]:
    """Mirror the dispatch tool catalog: native + MCP + connector.

    Without this, /api/runtime/context-meter/{session_id} undercounts
    the ``active_tools`` bucket for users with enabled connectors or
    MCP servers and disagrees with the runtime ``context_meter`` event
    the UI receives over websocket — the endpoint's stated parity
    contract.
    """
    names = list(_native_tool_names())
    names.extend(await _existing_mcp_tool_names(owner_uid))
    names.extend(await _connector_tool_names(owner_uid))
    return names


@router.get("/context-meter/{session_id}")
async def context_meter(session_id: str, request: Request) -> dict[str, Any]:
    """Return the projected loaded context footprint for a session.

    The response mirrors the `context_meter` runtime event emitted before
    every model run. It intentionally accounts for the same buckets the
    dispatch loop loads: system prompt, active tools (native + MCP +
    connector tools), checkpoints, workspace/memory placeholders,
    pending tool outputs, recent history, and the current user message
    placeholder.
    """
    user_uid = _current_user_uid(request)
    owner_uid = await _resolve_session_owner(session_id)
    if owner_uid is not None and owner_uid != user_uid:
        raise HTTPException(status_code=404, detail="Session not found")
    effective_owner = owner_uid or user_uid
    tool_names = await _effective_tool_names(effective_owner)
    prepared = await build_prepared_context(
        session_factory=_session_ctx,
        session_id=session_id,
        owner_uid=effective_owner,
        current_text="",
        instructions=DEFAULT_INSTRUCTIONS,
        tool_names=tool_names,
    )
    return prepared.meter


__all__ = ["router"]
