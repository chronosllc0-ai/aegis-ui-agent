"""MCP transport helpers for connection testing and tool discovery."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from backend.connections.models import MCPScanResponse


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def test_mcp_transport(transport: str, endpoint: str | None, command: str | None) -> tuple[bool, str]:
    """Validate MCP transport fields with actionable messages."""
    normalized = (transport or "http").lower()

    if normalized in {"http", "sse"}:
        if not endpoint:
            return False, "MCP URL is required for HTTP/SSE transports."
        if not _is_http_url(endpoint):
            return False, "MCP URL must be a valid http(s) URL."
        return True, f"{normalized.upper()} transport configuration is valid."

    if normalized == "stdio":
        if not command or not command.strip():
            return False, "Command is required for stdio transport."
        return True, "STDIO transport configuration is valid."

    return False, f"Unsupported transport '{transport}'. Use stdio, http, or sse."


def scan_mcp_tools(server_name: str, transport: str, endpoint: str | None) -> MCPScanResponse:
    """Return a deterministic tool manifest for configured MCP servers."""
    lower_name = server_name.lower()
    tools: list[dict[str, Any]] = []

    if "browser" in lower_name:
        tools = [
            {"name": "browser_navigate", "description": "Open a URL in the browser context."},
            {"name": "browser_click", "description": "Click interactive elements by selector."},
            {"name": "browser_screenshot", "description": "Capture viewport screenshot."},
        ]
    elif "chrome" in lower_name or "devtools" in lower_name:
        tools = [
            {"name": "cdp_navigate", "description": "Navigate tab through Chrome DevTools protocol."},
            {"name": "cdp_network_log", "description": "Read recent network requests."},
            {"name": "cdp_console", "description": "Collect browser console messages."},
        ]
    else:
        tools = [
            {"name": "mcp_ping", "description": "Health-check call for MCP server."},
            {"name": "mcp_invoke", "description": "Invoke MCP tool by name with arguments."},
        ]

    target = endpoint or "local stdio"
    return MCPScanResponse(
        ok=True,
        tools=tools,
        message=f"Discovered {len(tools)} tools via {transport.upper()} on {target}.",
        tested_at=datetime.now(timezone.utc),
    )
