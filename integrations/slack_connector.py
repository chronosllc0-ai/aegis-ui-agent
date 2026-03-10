"""Slack Web API integration."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from integrations.base import BaseIntegration, IntegrationError, RateLimitedError
from integrations.models import IntegrationRecord, ToolDefinition, ToolExecutionResult


class SlackIntegration(BaseIntegration):
    """Slack connector using Web API endpoints."""

    kind = "slack"
    base_url = "https://slack.com/api"

    async def _call(self, token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json;charset=utf-8"}
        url = f"{self.base_url}/{method}"
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "1"))
                await asyncio.sleep(retry_after)
                response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok", False):
            raise IntegrationError(str(body.get("error", f"Slack {method} failed")))
        return body

    async def connect(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        token = secrets.get("bot_token") or secrets.get("oauth_token") or ""
        if not token:
            raise IntegrationError("Slack bot token is required")
        auth = await self._call(token, "auth.test", {})
        return {"connected": True, "team": auth.get("team"), "user": auth.get("user")}

    async def disconnect(self, record: IntegrationRecord) -> None:
        return None

    async def health_check(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        token = secrets.get("bot_token") or secrets.get("oauth_token") or ""
        auth = await self._call(token, "auth.test", {})
        return {"ok": True, "team": auth.get("team"), "user": auth.get("user")}

    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("slack.auth_test", "Validate token and return workspace identity."),
            ToolDefinition("slack.list_conversations", "List channels/DM conversations."),
            ToolDefinition("slack.read_messages", "Read recent messages for a conversation."),
            ToolDefinition("slack.post_message", "Post message into a conversation."),
        ]

    async def execute_tool(
        self,
        record: IntegrationRecord,
        secrets: dict[str, str],
        tool_name: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        token = secrets.get("bot_token") or secrets.get("oauth_token") or ""
        if not token:
            return ToolExecutionResult(ok=False, tool=tool_name, error="Missing Slack token")
        try:
            if tool_name == "slack.auth_test":
                body = await self._call(token, "auth.test", {})
                data = body
            elif tool_name == "slack.list_conversations":
                body = await self._call(token, "conversations.list", {"limit": int(params.get("limit", 50)), "types": params.get("types", "public_channel,private_channel,im,mpim")})
                data = {"channels": body.get("channels", [])}
            elif tool_name == "slack.read_messages":
                body = await self._call(token, "conversations.history", {"channel": params.get("channel"), "limit": int(params.get("limit", 20))})
                data = {"messages": body.get("messages", [])}
            elif tool_name == "slack.post_message":
                body = await self._call(token, "chat.postMessage", {"channel": params.get("channel"), "text": params.get("text", "")})
                data = body.get("message", {})
            else:
                raise IntegrationError(f"Unsupported slack tool: {tool_name}")
            return ToolExecutionResult(ok=True, tool=tool_name, data=data)
        except (IntegrationError, RateLimitedError, httpx.HTTPError) as exc:
            return ToolExecutionResult(ok=False, tool=tool_name, error=str(exc))
