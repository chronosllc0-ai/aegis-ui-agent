"""Routes for MCP preset expansion and admin connection wizard actions."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

import auth
from backend.admin.dependencies import get_admin_user
from backend.connections.models import (
    AdminConnectionDraftPayload,
    ConnectionTemplate,
    ConnectionTestPayload,
    MCPCustomCreatePayload,
    MCPPresetApplyPayload,
    MCPServerConfig,
)
from backend.connections.service import list_published_mcp_presets, list_user_mcp_servers, scan_tools_for_server, test_connection
from backend.database import User, get_session
from backend.key_management import KeyManager
from config import settings

router = APIRouter(prefix="/api", tags=["connections"])
_key_manager = KeyManager(settings.ENCRYPTION_SECRET)


def _session_user(request: Request) -> dict[str, Any]:
    token = request.cookies.get("aegis_session")
    payload = auth._verify_session(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload


@router.get("/mcp/presets")
async def get_mcp_presets(
    session: AsyncSession = Depends(get_session),
    payload: dict[str, Any] = Depends(_session_user),
) -> dict[str, Any]:
    """List globally published MCP presets with user-specific add status."""
    presets = await list_published_mcp_presets(session)
    user_servers = await list_user_mcp_servers(session, str(payload["uid"]))
    by_preset = {server.get("preset_id"): server for server in user_servers if server.get("preset_id")}
    for preset in presets:
        attached = by_preset.get(preset["id"])
        preset["user_status"] = attached.get("status") if attached else "not_added"
    return {"ok": True, "presets": presets}


@router.get("/mcp/servers")
async def get_user_mcp_servers(
    session: AsyncSession = Depends(get_session),
    payload: dict[str, Any] = Depends(_session_user),
) -> dict[str, Any]:
    """List user-scoped MCP server instances."""
    servers = await list_user_mcp_servers(session, str(payload["uid"]))
    return {"ok": True, "servers": servers}


@router.post("/mcp/servers/from-preset")
async def create_mcp_server_from_preset(
    body: MCPPresetApplyPayload,
    session: AsyncSession = Depends(get_session),
    payload: dict[str, Any] = Depends(_session_user),
) -> dict[str, Any]:
    """Instantiate a user MCP server from a globally published preset."""
    preset = await session.get(ConnectionTemplate, body.preset_id)
    if not preset or preset.connection_type != "mcp" or not preset.published:
        raise HTTPException(status_code=404, detail="MCP preset not found")

    existing = (
        await session.execute(
            MCPServerConfig.__table__.select().where(
                MCPServerConfig.user_id == str(payload["uid"]),
                MCPServerConfig.preset_id == preset.id,
            )
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Preset already added")

    config = json.loads(preset.config_json or "{}")
    server = MCPServerConfig(
        user_id=str(payload["uid"]),
        name=preset.name,
        description=preset.description,
        logo_url=preset.logo_url,
        source_type="global_preset",
        owner_scope="global",
        preset_id=preset.id,
        transport=str(config.get("transport", "http")),
        endpoint=str(config.get("endpoint", "")).strip() or None,
        command=str(config.get("command", "")).strip() or None,
        args_json=json.dumps(config.get("args", [])),
        auth_type=str(config.get("auth_type", "none")),
        status="added",
        tools_json=json.dumps([]),
    )
    session.add(server)
    await session.commit()
    await session.refresh(server)
    return {"ok": True, "server_id": server.id, "status": server.status}


@router.post("/mcp/servers/custom")
async def create_custom_mcp_server(
    body: MCPCustomCreatePayload,
    session: AsyncSession = Depends(get_session),
    payload: dict[str, Any] = Depends(_session_user),
) -> dict[str, Any]:
    """Create a user-scoped custom MCP server."""
    encrypted_secret = _key_manager.encrypt(body.api_key) if body.api_key else None
    server = MCPServerConfig(
        user_id=str(payload["uid"]),
        name=body.name.strip(),
        description=f"Custom MCP server at {body.server_url.strip()}",
        source_type="user_custom",
        owner_scope="user",
        transport="http",
        endpoint=body.server_url.strip(),
        auth_type=body.auth_type,
        secret_ref=encrypted_secret,
        status="added",
        tools_json=json.dumps([]),
    )
    session.add(server)
    await session.commit()
    await session.refresh(server)
    return {"ok": True, "server": {"id": server.id, "name": server.name, "status": server.status}}


@router.post("/mcp/servers/{server_id}/scan")
async def scan_mcp_server_tools(
    server_id: str,
    session: AsyncSession = Depends(get_session),
    payload: dict[str, Any] = Depends(_session_user),
) -> dict[str, Any]:
    """Scan MCP tools for a user server and persist discovered manifest."""
    server = await session.get(MCPServerConfig, server_id)
    if not server or server.user_id != str(payload["uid"]):
        raise HTTPException(status_code=404, detail="MCP server not found")

    args: list[str] = []
    try:
        parsed = json.loads(server.args_json or "[]")
        if isinstance(parsed, list):
            args = [str(x) for x in parsed]
    except json.JSONDecodeError:
        args = []

    result = await scan_tools_for_server(
        server.id,
        server.name,
        server.transport,
        server.endpoint,
        command=server.command,
        args=args,
    )
    server.tools_json = json.dumps(result["tools"])
    if result["ok"]:
        server.status = "connected"
        server.last_error = None
    else:
        server.status = "error"
        server.last_error = result.get("error") or result.get("message")
    await session.commit()
    return {"ok": result["ok"], **result}


@router.post("/mcp/servers/{server_id}/test")
async def test_mcp_server(
    server_id: str,
    session: AsyncSession = Depends(get_session),
    payload: dict[str, Any] = Depends(_session_user),
) -> dict[str, Any]:
    """Run MCP transport test and store status/errors."""
    server = await session.get(MCPServerConfig, server_id)
    if not server or server.user_id != str(payload["uid"]):
        raise HTTPException(status_code=404, detail="MCP server not found")

    ok, message = await test_connection(
        "mcp",
        {
            "transport": server.transport,
            "url": server.endpoint,
            "command": server.command,
        },
    )
    server.status = "connected" if ok else "error"
    server.last_error = None if ok else message
    await session.commit()
    return {"ok": ok, "message": message, "error": None if ok else message}


@router.get("/admin/connections")
async def list_admin_connections(
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List admin connection templates for the wizard surface."""
    rows = (await session.execute(ConnectionTemplate.__table__.select().order_by(ConnectionTemplate.updated_at.desc()))).fetchall()
    data = []
    for row in rows:
        rec = row._mapping
        data.append(
            {
                "id": rec["id"],
                "name": rec["name"],
                "subtitle": rec["subtitle"],
                "description": rec["description"],
                "logo_url": rec["logo_url"],
                "connection_type": rec["connection_type"],
                "config": json.loads(rec["config_json"] or "{}"),
                "status": rec["status"],
                "published": bool(rec["published"]),
            }
        )
    return {"ok": True, "connections": data}


@router.post("/admin/connections")
async def create_admin_connection(
    body: AdminConnectionDraftPayload,
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create admin connection draft or directly published record."""
    record = ConnectionTemplate(
        name=body.name.strip(),
        subtitle=(body.subtitle or "").strip() or None,
        description=(body.description or "").strip() or None,
        logo_url=(body.logo_url or "").strip() or None,
        connection_type=body.connection_type,
        config_json=json.dumps(body.config),
        status=body.status,
        published=body.status == "published",
        created_by=admin.uid,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return {"ok": True, "connection_id": record.id, "status": record.status}


@router.put("/admin/connections/{connection_id}")
async def update_admin_connection(
    connection_id: str,
    body: AdminConnectionDraftPayload,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update an admin connection draft with autosave support."""
    record = await session.get(ConnectionTemplate, connection_id)
    if not record:
        raise HTTPException(status_code=404, detail="Connection not found")

    record.name = body.name.strip()
    record.subtitle = (body.subtitle or "").strip() or None
    record.description = (body.description or "").strip() or None
    record.logo_url = (body.logo_url or "").strip() or None
    record.connection_type = body.connection_type
    record.config_json = json.dumps(body.config)
    record.status = body.status
    record.published = body.status == "published"
    await session.commit()
    return {"ok": True, "connection_id": record.id, "status": record.status}


@router.post("/admin/connections/test")
async def test_admin_connection(
    body: ConnectionTestPayload,
    _: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """Run connection test endpoint used by wizard step 4."""
    ok, message = await test_connection(body.connection_type, body.config)
    return {"ok": ok, "message": message, "error": None if ok else message}
