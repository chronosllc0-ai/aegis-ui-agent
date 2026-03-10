"""Discord MCP-style integration stub."""

from __future__ import annotations

from typing import Any

from integrations.base import BaseIntegration


class DiscordIntegration(BaseIntegration):
    """Discord connector with mocked tool execution."""

    name = "discord"

    def __init__(self) -> None:
        self.connected = False

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        self.connected = bool(config.get("bot_token"))
        return {"connected": self.connected, "guild": config.get("guild_id", "mock-guild") if self.connected else None}

    async def disconnect(self) -> None:
        self.connected = False

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "discord_get_messages", "description": "Fetch channel messages"},
            {"name": "discord_send_message", "description": "Send message"},
            {"name": "discord_list_channels", "description": "List channels in guild"},
            {"name": "discord_send_file", "description": "Send file"},
        ]

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": self.connected, "tool": tool_name, "params": params, "result": "mock_discord_response"}
