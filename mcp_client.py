"""MCP client registry and tool proxying."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from integrations import DiscordIntegration, SlackIntegration, TelegramIntegration
from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)


@dataclass
class MCPServer:
    """Connected MCP server metadata."""

    server_id: str
    name: str
    enabled: bool = True
    tool_manifest: list[dict[str, Any]] = field(default_factory=list)
    connector: BaseIntegration | None = None


class MCPClient:
    """Minimal MCP client that stores user-scoped server configs and tools."""

    def __init__(self) -> None:
        self.user_servers: dict[str, dict[str, MCPServer]] = {}

    async def connect_builtin(self, user_id: str, integration_name: str, config: dict[str, Any]) -> MCPServer:
        connector_map: dict[str, BaseIntegration] = {
            "telegram": TelegramIntegration(),
            "slack": SlackIntegration(),
            "discord": DiscordIntegration(),
        }
        connector = connector_map[integration_name]
        status = await connector.connect(config)
        server = MCPServer(
            server_id=f"{integration_name}-{user_id}",
            name=integration_name,
            enabled=bool(status.get("connected", False)),
            tool_manifest=connector.list_tools(),
            connector=connector,
        )
        self.user_servers.setdefault(user_id, {})[server.server_id] = server
        return server

    async def register_custom_server(self, user_id: str, server_id: str, name: str, tools: list[dict[str, Any]]) -> MCPServer:
        server = MCPServer(server_id=server_id, name=name, tool_manifest=tools)
        self.user_servers.setdefault(user_id, {})[server_id] = server
        return server

    async def list_tools(self, user_id: str) -> list[dict[str, Any]]:
        servers = self.user_servers.get(user_id, {})
        return [tool | {"server_id": server.server_id} for server in servers.values() if server.enabled for tool in server.tool_manifest]

    async def execute_tool(self, user_id: str, server_id: str, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        servers = self.user_servers.get(user_id, {})
        server = servers.get(server_id)
        if server is None or server.connector is None:
            raise ValueError(f"Unknown server: {server_id}")
        try:
            return await asyncio.wait_for(server.connector.execute_tool(tool_name, params), timeout=8)
        except TimeoutError:
            logger.warning("Timeout executing MCP tool %s on %s", tool_name, server_id)
            return {"ok": False, "error": "timeout", "tool": tool_name}
