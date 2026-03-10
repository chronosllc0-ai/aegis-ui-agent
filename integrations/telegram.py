"""Telegram MCP-style integration stub."""

from __future__ import annotations

from typing import Any

from integrations.base import BaseIntegration


class TelegramIntegration(BaseIntegration):
    """Telegram connector with mocked tool execution."""

    name = "telegram"

    def __init__(self) -> None:
        self.connected = False

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        self.connected = bool(config.get("bot_token"))
        return {"connected": self.connected, "bot_username": "@aegis_mock_bot" if self.connected else None}

    async def disconnect(self) -> None:
        self.connected = False

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "telegram_get_messages", "description": "Fetch recent messages"},
            {"name": "telegram_send_message", "description": "Send a message"},
            {"name": "telegram_send_image", "description": "Send image data"},
            {"name": "telegram_list_chats", "description": "List chats"},
        ]

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": self.connected, "tool": tool_name, "params": params, "result": "mock_telegram_response"}
