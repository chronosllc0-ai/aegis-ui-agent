"""Discord MCP-style integration client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"

class DiscordIntegration(BaseIntegration):
    """Discord connector with real API calls."""

    name = "discord"

    def __init__(self) -> None:
        self.connected = False
        self._token: str | None = None
        self._guild_id: str | None = None

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate the bot token and cache guild metadata."""
        token = str(config.get("bot_token", "")).strip()
        guild_id = str(config.get("guild_id", "")).strip()
        self._token = token or None
        self._guild_id = guild_id or None
        if not self._token:
            self.connected = False
            return {"connected": False, "guild": None, "error": "Missing bot token"}

        try:
            data = await self._request("GET", "/users/@me")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Discord auth failed: %s", exc)
            self.connected = False
            return {"connected": False, "guild": self._guild_id, "error": str(exc)}

        if "id" in data:
            self.connected = True
            return {"connected": True, "guild": self._guild_id}

        self.connected = False
        return {"connected": False, "guild": self._guild_id, "error": data.get("message") or "Auth failed"}

    async def disconnect(self) -> None:
        self.connected = False
        self._token = None
        self._guild_id = None

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "discord_get_messages", "description": "Fetch recent channel messages"},
            {"name": "discord_send_message", "description": "Send a message to a channel"},
            {"name": "discord_list_channels", "description": "List channels in a guild"},
            {"name": "discord_send_file", "description": "Upload a file to a channel"},
        ]

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.connected or not self._token:
            return {"ok": False, "tool": tool_name, "error": "Discord integration is not connected"}

        if tool_name == "discord_list_channels":
            return await self._list_channels(params)
        if tool_name == "discord_get_messages":
            return await self._get_messages(params)
        if tool_name == "discord_send_message":
            return await self._send_message(params)
        if tool_name == "discord_send_file":
            return {"ok": False, "tool": tool_name, "error": "File upload is not implemented"}

        return {"ok": False, "tool": tool_name, "error": "Unsupported tool"}

    async def _list_channels(self, params: dict[str, Any]) -> dict[str, Any]:
        guild_id = str(params.get("guild_id", "")).strip() or self._guild_id
        if not guild_id:
            return {"ok": False, "tool": "discord_list_channels", "error": "Guild ID is required"}
        data = await self._request("GET", f"/guilds/{guild_id}/channels")
        ok = isinstance(data, list)
        return {"ok": ok, "tool": "discord_list_channels", "result": data}

    async def _get_messages(self, params: dict[str, Any]) -> dict[str, Any]:
        channel = str(params.get("channel", "")).strip()
        if not channel:
            return {"ok": False, "tool": "discord_get_messages", "error": "Channel is required"}
        limit = int(params.get("limit", 20))
        data = await self._request("GET", f"/channels/{channel}/messages", params={"limit": limit})
        ok = isinstance(data, list)
        return {"ok": ok, "tool": "discord_get_messages", "result": data}

    async def _send_message(self, params: dict[str, Any]) -> dict[str, Any]:
        channel = str(params.get("channel", "")).strip()
        text = str(params.get("text", "")).strip()
        if not channel:
            return {"ok": False, "tool": "discord_send_message", "error": "Channel is required"}
        if not text:
            return {"ok": False, "tool": "discord_send_message", "error": "Text is required"}
        data = await self._request("POST", f"/channels/{channel}/messages", json={"content": text})
        ok = bool(data.get("id")) if isinstance(data, dict) else False
        return {"ok": ok, "tool": "discord_send_message", "result": data}

    async def send_image(self, channel: str, image_b64: str) -> dict[str, Any]:
        """Send a base64-encoded PNG to a Discord channel."""
        import base64, io
        url = f"{DISCORD_API_BASE}/channels/{channel}/messages"
        headers = {"Authorization": f"Bot {self._token}"}
        image_bytes = base64.b64decode(image_b64)
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                url,
                headers=headers,
                files={"file": ("frame.png", io.BytesIO(image_bytes), "image/png")},
            )
        try:
            data = response.json()
        except ValueError:
            data = {"message": response.text}
        return {"ok": bool(data.get("id")) if isinstance(data, dict) else False, "result": data}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        if not self._token:
            return {"message": "Missing bot token"}

        url = f"{DISCORD_API_BASE}{path}"
        headers = {"Authorization": f"Bot {self._token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(method, url, headers=headers, params=params, json=json)

        try:
            data = response.json()
        except ValueError:
            data = {"message": response.text}

        if response.status_code >= 400:
            error = data.get("message") if isinstance(data, dict) else response.text
            return {"message": error or f"HTTP {response.status_code}", "status": response.status_code}

        return data
