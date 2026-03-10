"""Telegram Bot API integration using raw HTTP calls."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from integrations.base import BaseIntegration, IntegrationError
from integrations.models import IntegrationRecord, ToolDefinition, ToolExecutionResult


class TelegramIntegration(BaseIntegration):
    """Telegram connector supporting webhook and polling operations."""

    kind = "telegram"
    base_url = "https://api.telegram.org"

    def __init__(self) -> None:
        self._offsets: dict[str, int] = {}

    async def _call(
        self,
        token: str,
        method: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 12.0,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/bot{token}/{method}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload or {})
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise IntegrationError(str(body.get("description", f"Telegram {method} failed")))
        return body.get("result", {})

    async def connect(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        token = secrets.get("bot_token", "")
        if not token:
            raise IntegrationError("Telegram bot token is required")
        me = await self._call(token, "getMe")
        return {
            "connected": True,
            "bot_username": me.get("username"),
            "delivery_mode": record.config.get("delivery_mode", "polling"),
        }

    async def disconnect(self, record: IntegrationRecord) -> None:
        self._offsets.pop(record.user_id, None)

    async def health_check(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        token = secrets.get("bot_token", "")
        me = await self._call(token, "getMe")
        webhook_info = await self._call(token, "getWebhookInfo")
        return {
            "ok": True,
            "bot_username": me.get("username"),
            "delivery_mode": record.config.get("delivery_mode", "polling"),
            "webhook": webhook_info,
        }

    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("telegram.get_me", "Return bot identity."),
            ToolDefinition("telegram.get_webhook_info", "Return webhook configuration state."),
            ToolDefinition("telegram.set_webhook", "Set HTTPS webhook URL and optional secret token."),
            ToolDefinition("telegram.delete_webhook", "Delete webhook configuration."),
            ToolDefinition("telegram.get_updates", "Fetch updates via long polling."),
            ToolDefinition("telegram.send_message", "Send a text message."),
            ToolDefinition("telegram.send_message_draft", "Send draft update (Bot API 9.5) with draft_id."),
            ToolDefinition("telegram.send_chat_action", "Send typing action while composing response."),
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
            return ToolExecutionResult(ok=False, tool=tool_name, error="Missing Telegram token")

        try:
            if tool_name == "telegram.get_me":
                data = await self._call(token, "getMe")
            elif tool_name == "telegram.get_webhook_info":
                data = await self._call(token, "getWebhookInfo")
            elif tool_name == "telegram.set_webhook":
                webhook_url = str(params.get("url", "")).strip()
                if not webhook_url.startswith("https://"):
                    raise IntegrationError("Telegram webhook URL must be HTTPS")
                payload = {
                    "url": webhook_url,
                    "allowed_updates": params.get("allowed_updates") or [],
                }
                secret_token = str(params.get("secret_token", "")).strip()
                if secret_token:
                    payload["secret_token"] = secret_token
                data = await self._call(token, "setWebhook", payload)
            elif tool_name == "telegram.delete_webhook":
                data = await self._call(token, "deleteWebhook", {"drop_pending_updates": bool(params.get("drop_pending_updates", False))})
            elif tool_name == "telegram.get_updates":
                offset = int(params.get("offset") or self._offsets.get(record.user_id, 0))
                payload = {"offset": offset, "timeout": int(params.get("timeout", 2)), "allowed_updates": params.get("allowed_updates") or []}
                updates = await self._call(token, "getUpdates", payload, timeout=20.0)
                if updates:
                    self._offsets[record.user_id] = int(updates[-1].get("update_id", offset)) + 1
                data = {"updates": updates, "next_offset": self._offsets.get(record.user_id, offset)}
            elif tool_name == "telegram.send_chat_action":
                payload = {"chat_id": params.get("chat_id"), "action": params.get("action", "typing")}
                data = await self._call(token, "sendChatAction", payload)
            elif tool_name == "telegram.send_message":
                await self._call(token, "sendChatAction", {"chat_id": params.get("chat_id"), "action": "typing"})
                payload = {
                    "chat_id": params.get("chat_id"),
                    "text": params.get("text", ""),
                    "parse_mode": params.get("parse_mode"),
                }
                data = await self._call(token, "sendMessage", payload)
            elif tool_name == "telegram.send_message_draft":
                draft_id = int(params.get("draft_id", 0))
                if draft_id <= 0:
                    raise IntegrationError("draft_id must be a non-zero integer")
                payload = {
                    "chat_id": params.get("chat_id"),
                    "draft_id": draft_id,
                    "text": params.get("text", ""),
                    "message_thread_id": params.get("message_thread_id"),
                    "parse_mode": params.get("parse_mode"),
                    "entities": params.get("entities"),
                }
                try:
                    data = await self._call(token, "sendMessageDraft", payload)
                except Exception:
                    await self._call(token, "sendChatAction", {"chat_id": params.get("chat_id"), "action": "typing"})
                    data = await self._call(token, "sendMessage", {"chat_id": params.get("chat_id"), "text": params.get("text", "")})
            else:
                raise IntegrationError(f"Unsupported telegram tool: {tool_name}")

            return ToolExecutionResult(ok=True, tool=tool_name, data=data)
        except (IntegrationError, httpx.HTTPError, asyncio.TimeoutError) as exc:
            return ToolExecutionResult(ok=False, tool=tool_name, error=str(exc))

    def get_polling_offset(self, user_id: str) -> int:
        """Return current persisted polling offset for user."""
        return self._offsets.get(user_id, 0)
