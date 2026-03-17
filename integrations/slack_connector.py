"""Slack MCP-style integration client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"

class SlackIntegration(BaseIntegration):
    """Slack connector with real API calls."""

    name = "slack"

    def __init__(self) -> None:
        self.connected = False
        self._token: str | None = None
        self._workspace: str | None = None

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate the provided token and store workspace metadata."""
        token = str(config.get("bot_token") or config.get("oauth_token") or "").strip()
        workspace = str(config.get("workspace", "")).strip()
        self._token = token or None
        if not self._token:
            self.connected = False
            self._workspace = None
            return {"connected": False, "workspace": None, "error": "Missing token"}

        try:
            auth = await self._request("GET", "auth.test")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Slack auth test failed: %s", exc)
            self.connected = False
            self._workspace = None
            return {"connected": False, "workspace": None, "error": str(exc)}

        if auth.get("ok"):
            self.connected = True
            self._workspace = str(auth.get("team") or workspace or "") or None
            return {"connected": True, "workspace": self._workspace}

        self.connected = False
        self._workspace = workspace or None
        return {"connected": False, "workspace": self._workspace, "error": auth.get("error") or "Auth failed"}

    async def disconnect(self) -> None:
        self.connected = False
        self._token = None
        self._workspace = None

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "slack_get_messages", "description": "Fetch recent channel messages"},
            {"name": "slack_send_message", "description": "Post a message to a channel"},
            {"name": "slack_list_channels", "description": "List channels in the workspace"},
            {"name": "slack_send_file", "description": "Upload a file to a channel"},
        ]

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.connected or not self._token:
            return {"ok": False, "tool": tool_name, "error": "Slack integration is not connected"}

        if tool_name == "slack_list_channels":
            return await self._list_channels(params)
        if tool_name == "slack_get_messages":
            return await self._get_messages(params)
        if tool_name == "slack_send_message":
            return await self._send_message(params)
        if tool_name == "slack_send_file":
            return {"ok": False, "tool": tool_name, "error": "File upload is not implemented"}

        return {"ok": False, "tool": tool_name, "error": "Unsupported tool"}

    async def _list_channels(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = int(params.get("limit", 100))
        cursor = str(params.get("cursor", "")).strip() or None
        payload: dict[str, Any] = {"limit": limit, "types": "public_channel,private_channel"}
        if cursor:
            payload["cursor"] = cursor
        data = await self._request("GET", "conversations.list", params=payload)
        return {"ok": bool(data.get("ok")), "tool": "slack_list_channels", "result": data}

    async def _get_messages(self, params: dict[str, Any]) -> dict[str, Any]:
        channel = str(params.get("channel", "")).strip()
        if not channel:
            return {"ok": False, "tool": "slack_get_messages", "error": "Channel is required"}
        limit = int(params.get("limit", 20))
        payload = {"channel": channel, "limit": limit}
        data = await self._request("GET", "conversations.history", params=payload)
        return {"ok": bool(data.get("ok")), "tool": "slack_get_messages", "result": data}

    async def _send_message(self, params: dict[str, Any]) -> dict[str, Any]:
        channel = str(params.get("channel", "")).strip()
        text = str(params.get("text", "")).strip()
        if not channel:
            return {"ok": False, "tool": "slack_send_message", "error": "Channel is required"}
        if not text:
            return {"ok": False, "tool": "slack_send_message", "error": "Text is required"}
        data = await self._request("POST", "chat.postMessage", json={"channel": channel, "text": text})
        return {"ok": bool(data.get("ok")), "tool": "slack_send_message", "result": data}

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._token:
            return {"ok": False, "error": "Missing token"}

        url = f"{SLACK_API_BASE}/{endpoint}"
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(method, url, headers=headers, params=params, json=json)

        try:
            data = response.json()
        except ValueError:
            data = {"ok": False, "error": response.text}

        if response.status_code >= 400:
            error = data.get("error") if isinstance(data, dict) else response.text
            return {"ok": False, "error": error or f"HTTP {response.status_code}", "status": response.status_code}

        if isinstance(data, dict):
            return data
        return {"ok": False, "error": "Invalid response"}
