"""Business logic for admin connections and user MCP server management."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.connections.models import ConnectionTemplate, MCPServerConfig
from backend.mcp.transport import test_mcp_transport
from backend.runtime.tools.mcp_host import MCPServerSpec, scan_mcp_server

DEFAULT_MCP_PRESETS: list[dict[str, Any]] = [
    {
        "id": "preset-browsermcp",
        "name": "BrowserMCP",
        "subtitle": "Web browser automation",
        "description": "Browser automation primitives via @browsermcp/mcp, spawned as a stdio subprocess by the backend.",
        "logo_url": "https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/webassembly.svg",
        "connection_type": "mcp",
        "published": True,
        "status": "published",
        # Phase 3 PLAN.md §4 option (a): bundle @browsermcp/mcp as an
        # opt-in backend stdio subprocess. Operators flip the server on
        # by setting ``BROWSERMCP_ENABLED=true`` in the backend env.
        "config": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@browsermcp/mcp@latest"],
            "auth_type": "none",
        },
    },
    {
        "id": "preset-chrome-devtools-mcp",
        "name": "Chrome DevTools MCP",
        "subtitle": "Debug browser sessions",
        "description": "Connects to Chrome DevTools Protocol tooling for diagnostics.",
        "logo_url": "https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/googlechrome.svg",
        "connection_type": "mcp",
        "published": True,
        "status": "published",
        "config": {
            "transport": "sse",
            "endpoint": "http://localhost:9222/mcp",
            "auth_type": "none",
        },
    },
]


def _parse_json(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


async def ensure_default_mcp_presets(session: AsyncSession) -> None:
    """Seed built-in MCP presets so users/admins always have starter cards."""
    for preset in DEFAULT_MCP_PRESETS:
        existing = await session.get(ConnectionTemplate, preset["id"])
        if existing:
            continue
        session.add(
            ConnectionTemplate(
                id=preset["id"],
                name=preset["name"],
                subtitle=preset["subtitle"],
                description=preset["description"],
                logo_url=preset["logo_url"],
                connection_type="mcp",
                config_json=json.dumps(preset["config"]),
                status="published",
                published=True,
                created_by="system",
            )
        )
    await session.commit()


async def list_published_mcp_presets(session: AsyncSession) -> list[dict[str, Any]]:
    """Return globally published MCP presets available to all users."""
    rows = (
        await session.execute(
            select(ConnectionTemplate).where(
                ConnectionTemplate.connection_type == "mcp",
                ConnectionTemplate.published.is_(True),
            )
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "subtitle": row.subtitle,
            "description": row.description,
            "logo_url": row.logo_url,
            "connection_type": row.connection_type,
            "status": row.status,
            "config": _parse_json(row.config_json, {}),
        }
        for row in rows
    ]


async def list_user_mcp_servers(session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
    """Return all user MCP servers, including preset instances and custom entries."""
    rows = (
        await session.execute(select(MCPServerConfig).where(MCPServerConfig.user_id == user_id).order_by(MCPServerConfig.created_at.desc()))
    ).scalars().all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "logo_url": row.logo_url,
            "source_type": row.source_type,
            "owner_scope": row.owner_scope,
            "preset_id": row.preset_id,
            "transport": row.transport,
            "endpoint": row.endpoint,
            "command": row.command,
            "args": _parse_json(row.args_json, []),
            "auth_type": row.auth_type,
            "status": row.status,
            "last_error": row.last_error,
            "tools": _parse_json(row.tools_json, []),
        }
        for row in rows
    ]


async def test_connection(connection_type: str, config: dict[str, Any]) -> tuple[bool, str]:
    """Execute lightweight but real validation for each connection type."""
    if connection_type == "oauth":
        auth_url = str(config.get("auth_url", "")).strip()
        token_url = str(config.get("token_url", "")).strip()
        if not auth_url or not token_url:
            return False, "OAuth requires both auth URL and token URL."
        parsed_auth = urlparse(auth_url)
        parsed_token = urlparse(token_url)
        if parsed_auth.scheme not in {"http", "https"} or not parsed_auth.netloc:
            return False, "OAuth auth URL must be a valid http(s) URL."
        if parsed_token.scheme not in {"http", "https"} or not parsed_token.netloc:
            return False, "OAuth token URL must be a valid http(s) URL."
        return True, "OAuth configuration looks valid and ready to publish."

    if connection_type == "bot":
        provider = str(config.get("provider", "")).strip()
        token = str(config.get("token", "")).strip()
        webhook = str(config.get("webhook_url", "")).strip()
        if not provider:
            return False, "Bot provider is required."
        if not token and not webhook:
            return False, "Bot configuration requires either token or webhook URL."
        return True, f"Bot configuration for {provider} is valid."

    if connection_type == "mcp":
        ok, message = test_mcp_transport(
            str(config.get("transport", "http")),
            str(config.get("url", "")).strip() or None,
            str(config.get("command", "")).strip() or None,
        )
        return ok, message

    return False, f"Unsupported connection type '{connection_type}'."


async def scan_tools_for_server(
    server_id: str,
    name: str,
    transport: str,
    endpoint: str | None,
    command: str | None = None,
    args: list[str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run a live MCP ``tools/list`` scan and return a serialized payload.

    Phase 3 replaces the deprecated fixture-based ``scan_mcp_tools`` with
    a real SDK round-trip. The return shape is preserved so existing
    callers (the admin router, the test suite) keep working.
    """
    spec = MCPServerSpec(
        server_id=server_id,
        transport=(transport or "http").lower(),
        command=(command or "").strip() or None,
        args=tuple(args or ()),
        endpoint=(endpoint or "").strip() or None,
        headers=dict(headers or {}),
        display_name=name,
    )
    report = await scan_mcp_server(spec)
    return {
        "ok": report.ok,
        "tools": report.tools,
        "message": report.message,
        "error": report.error,
        "tested_at": report.tested_at.isoformat(),
    }
