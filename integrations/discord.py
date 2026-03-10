"""Discord REST API integration with basic rate-limit handling."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from integrations.base import BaseIntegration, IntegrationError
from integrations.models import IntegrationRecord, ToolDefinition, ToolExecutionResult


class DiscordIntegration(BaseIntegration):
    """Discord bot integration via REST API v10."""

    kind = "discord"
    base_url = "https://discord.com/api/v10"

    def __init__(self) -> None:
        self.last_rate_limit_incident: dict[str, Any] | None = None

    async def _request(self, token: str, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.request(method, url, headers=headers, json=payload)
            if response.status_code == 429:
                body = response.json()
                retry_after = float(response.headers.get("Retry-After") or body.get("retry_after", 1))
                self.last_rate_limit_incident = {
                    "retry_after": retry_after,
                    "global": bool(body.get("global", False)),
                    "bucket": response.headers.get("X-RateLimit-Bucket"),
                }
                await asyncio.sleep(retry_after)
                response = await client.request(method, url, headers=headers, json=payload)
        response.raise_for_status()
        if response.text:
            return response.json()
        return {}

    async def connect(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        token = secrets.get("bot_token", "")
        if not token:
            raise IntegrationError("Discord bot token is required")
        me = await self._request(token, "GET", "/users/@me")
        return {"connected": True, "username": me.get("username"), "id": me.get("id")}

    async def disconnect(self, record: IntegrationRecord) -> None:
        return None

    async def health_check(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        token = secrets.get("bot_token", "")
        me = await self._request(token, "GET", "/users/@me")
        return {"ok": True, "username": me.get("username"), "last_rate_limit": self.last_rate_limit_incident}

    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("discord.get_me", "Validate bot identity."),
            ToolDefinition("discord.read_messages", "Read channel messages."),
            ToolDefinition("discord.send_message", "Send channel message."),
            ToolDefinition("discord.send_typing", "Send typing indicator."),
        ]

    async def execute_tool(
        self,
        record: IntegrationRecord,
        secrets: dict[str, str],
        tool_name: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        token = secrets.get("bot_token", "")
        if not token:
            return ToolExecutionResult(ok=False, tool=tool_name, error="Missing Discord token")
        try:
            if tool_name == "discord.get_me":
                data = await self._request(token, "GET", "/users/@me")
            elif tool_name == "discord.read_messages":
                channel_id = str(params.get("channel_id", ""))
                limit = int(params.get("limit", 20))
                data = await self._request(token, "GET", f"/channels/{channel_id}/messages?limit={limit}")
            elif tool_name == "discord.send_message":
                channel_id = str(params.get("channel_id", ""))
                data = await self._request(token, "POST", f"/channels/{channel_id}/messages", {"content": params.get("text", "")})
            elif tool_name == "discord.send_typing":
                channel_id = str(params.get("channel_id", ""))
                data = await self._request(token, "POST", f"/channels/{channel_id}/typing")
            else:
                raise IntegrationError(f"Unsupported discord tool: {tool_name}")
            return ToolExecutionResult(ok=True, tool=tool_name, data=data)
        except (IntegrationError, httpx.HTTPError) as exc:
            return ToolExecutionResult(ok=False, tool=tool_name, error=str(exc))
