"""MCP transport helpers for connection testing.

Phase 3 removed the deprecated ``scan_mcp_tools`` fixture generator
from this module. Live tool discovery now goes through
:class:`backend.runtime.tools.mcp_host.MCPToolProvider.scan` (and the
lower-level :func:`backend.runtime.tools.mcp_host.scan_mcp_server`),
which dials a real MCP server over stdio / HTTP / SSE via the official
``mcp`` Python SDK.

The :func:`test_mcp_transport` validator survives as a cheap
pre-flight check used by the admin connection wizard.
"""

from __future__ import annotations

from urllib.parse import urlparse


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def test_mcp_transport(transport: str, endpoint: str | None, command: str | None) -> tuple[bool, str]:
    """Validate MCP transport fields with actionable messages."""
    normalized = (transport or "").strip().lower()
    if normalized not in {"stdio", "http", "sse"}:
        return False, f"Unsupported transport '{transport}'. Use stdio, http, or sse."

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

    return False, "Invalid MCP transport configuration."
