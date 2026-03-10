"""Slack MCP-style integration stub."""

from __future__ import annotations

from typing import Any

from integrations.base import BaseIntegration


class SlackIntegration(BaseIntegration):
    """Slack connector with mocked tool execution."""

    name = "slack"

    def __init__(self) -> None:
        self.connected = False

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        self.connected = bool(config.get("bot_token") or config.get("oauth_token"))
        return {"connected": self.connected, "workspace": "mock-workspace" if self.connected else None}

    async def disconnect(self) -> None:
        self.connected = False

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "slack_get_messages", "description": "Fetch channel messages"},
            {"name": "slack_send_message", "description": "Post message"},
            {"name": "slack_list_channels", "description": "List channels"},
            {"name": "slack_send_file", "description": "Upload file"},
        ]

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": self.connected, "tool": tool_name, "params": params, "result": "mock_slack_response"}
