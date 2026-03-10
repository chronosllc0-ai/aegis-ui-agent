"""Compatibility MCP client wrapper around IntegrationManager custom MCP services."""

from __future__ import annotations

from typing import Any

from integrations.manager import IntegrationManager


class MCPClient:
    """Backward-compatible adapter retained for orchestrator wiring."""

    def __init__(self) -> None:
        self.manager = IntegrationManager()

    async def register_custom_server(self, user_id: str, server_id: str, name: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Register placeholder custom server metadata for legacy callers."""
        return {
            "server_id": server_id,
            "name": name,
            "tool_count": len(tools),
            "tools": tools,
            "note": "Legacy path; use IntegrationManager MCP endpoints for live connections.",
        }

    async def list_tools(self, user_id: str) -> list[dict[str, Any]]:
        """List MCP tools for connected custom servers."""
        servers = self.manager.list_mcp_servers(user_id)
        tools: list[dict[str, Any]] = []
        for server in servers:
            tools.append({"server_id": server["server_id"], "name": "mcp_call_tool", "description": f"Call tool on {server['name']}"})
        return tools

    async def execute_tool(self, user_id: str, server_id: str, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Forward tool call to custom MCP server."""
        return await self.manager.execute_mcp_server(user_id, server_id, tool_name, params)
