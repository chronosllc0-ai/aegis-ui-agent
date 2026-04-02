"""Telegram MCP-style integration client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any

import httpx

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"

@dataclass
class TelegramConfig:
    """Telegram integration runtime configuration."""

    bot_token: str
    webhook_secret: str = ""
    polling_offset: int = 0


class TelegramAPIError(RuntimeError):
    """Raised when the Telegram Bot API returns an error payload."""

    def __init__(self, error_code: int | None, description: str) -> None:
        super().__init__(description)
        self.error_code = error_code
        self.description = description


class TelegramClient:
    """Thin async Telegram Bot API client used by integration + tests."""

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token
        self._client = httpx.AsyncClient(timeout=10)

    async def close(self) -> None:
        await self._client.aclose()

    async def _post(self, method: str, *, data: dict[str, Any] | None = None, json: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{TELEGRAM_API_BASE}/bot{self._token}/{method}"
        response = await self._client.post(url, data=data, json=json)
        payload = response.json()
        if not payload.get("ok"):
            raise TelegramAPIError(payload.get("error_code"), str(payload.get("description") or "Telegram API error"))
        return payload

    async def send_message(self, *, chat_id: Any, text: str, parse_mode: str | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode
        payload = await self._post("sendMessage", data=data)
        return payload.get("result", {})

    async def send_message_draft(self, *, chat_id: Any, draft_id: int, text: str) -> bool:
        if draft_id <= 0:
            raise ValueError("draft_id must be non-zero")
        payload = await self._post("sendMessageDraft", data={"chat_id": chat_id, "draft_id": draft_id, "text": text})
        return bool(payload.get("result", True))

    async def set_chat_member_tag(self, *, chat_id: Any, user_id: Any, tag: str) -> bool:
        payload = await self._post("setChatMemberTag", data={"chat_id": chat_id, "user_id": user_id, "tag": tag})
        return bool(payload.get("result", True))

    async def send_chat_action(self, chat_id: Any, action: str) -> bool:
        payload = await self._post("sendChatAction", data={"chat_id": chat_id, "action": action})
        return bool(payload.get("result", True))


class TelegramIntegration(BaseIntegration):
    """Telegram connector with real API calls."""

    name = "telegram"

    def __init__(self, config: TelegramConfig | None = None) -> None:
        self.connected = False
        self.config = config or TelegramConfig(bot_token="")
        self._token: str | None = self.config.bot_token or None
        self._delivery_mode: str = "polling"
        self._webhook_url: str | None = None
        self._webhook_secret: str | None = self.config.webhook_secret or None
        self.client: TelegramClient | None = TelegramClient(self._token) if self._token else None

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        token = str(config.get("bot_token", "")).strip()
        self.config.bot_token = token
        self._token = token or None
        self._delivery_mode = str(config.get("delivery_mode", "polling")).strip() or "polling"
        self._webhook_url = str(config.get("webhook_url", "")).strip() or None
        self._webhook_secret = str(config.get("webhook_secret", "")).strip() or None
        self.config.webhook_secret = self._webhook_secret or ""
        if self._token:
            if self.client:
                await self.client.close()
            self.client = TelegramClient(self._token)

        if not self._token:
            self.connected = False
            return {"connected": False, "bot_username": None, "error": "Missing bot token"}

        try:
            info = await self._request("getMe")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram getMe failed: %s", exc)
            self.connected = False
            return {"connected": False, "bot_username": None, "error": str(exc)}

        if not info.get("ok"):
            self.connected = False
            return {"connected": False, "bot_username": None, "error": info.get("description") or "Auth failed"}

        self.connected = True
        username = info.get("result", {}).get("username")

        if self._delivery_mode == "webhook" and self._webhook_url:
            await self._request(
                "setWebhook",
                json={
                    "url": self._webhook_url,
                    "secret_token": self._webhook_secret,
                    "drop_pending_updates": True,
                },
            )
        elif self._delivery_mode == "polling":
            await self._request("deleteWebhook", json={"drop_pending_updates": True})

        return {"connected": True, "bot_username": f"@{username}" if username else None}

    async def disconnect(self) -> None:
        self.connected = False
        self._token = None
        self._webhook_url = None
        self._webhook_secret = None
        if self.client:
            await self.client.close()
            self.client = None

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "telegram_get_messages", "description": "Fetch recent messages"},
            {"name": "telegram_send_message", "description": "Send a message"},
            {"name": "telegram_send_image", "description": "Send image data"},
            {"name": "telegram_list_chats", "description": "List chats"},
        ]

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.connected or not self._token:
            return {"ok": False, "tool": tool_name, "error": "Telegram integration is not connected"}

        if tool_name == "telegram_list_chats":
            return await self._list_chats(params)
        if tool_name == "telegram_get_messages":
            return await self._get_messages(params)
        if tool_name == "telegram_send_message":
            return await self._send_message(params)
        if tool_name == "telegram_send_image":
            return {"ok": False, "tool": tool_name, "error": "Image sending is not implemented"}

        return {"ok": False, "tool": tool_name, "error": "Unsupported tool"}

    async def _list_chats(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = int(params.get("limit", 20))
        data = await self._request("getUpdates", params={"limit": limit})
        return {"ok": bool(data.get("ok")), "tool": "telegram_list_chats", "result": data}

    async def _get_messages(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = int(params.get("limit", 20))
        offset = params.get("offset")
        payload: dict[str, Any] = {"limit": limit}
        if offset is not None:
            payload["offset"] = offset
        data = await self._request("getUpdates", params=payload)
        return {"ok": bool(data.get("ok")), "tool": "telegram_get_messages", "result": data}

    async def _send_message(self, params: dict[str, Any]) -> dict[str, Any]:
        chat_id = params.get("chat_id")
        text = str(params.get("text", "")).strip()
        if chat_id is None:
            return {"ok": False, "tool": "telegram_send_message", "error": "chat_id is required"}
        if not text:
            return {"ok": False, "tool": "telegram_send_message", "error": "Text is required"}
        data = await self._request("sendMessage", json={"chat_id": chat_id, "text": text})
        return {"ok": bool(data.get("ok")), "tool": "telegram_send_message", "result": data}

    async def set_my_commands(self, commands: list[dict[str, str]]) -> dict[str, Any]:
        """Register slash commands with Telegram BotFather API."""
        return await self._request("setMyCommands", json={"commands": commands})

    def validate_webhook_secret(self, secret: str) -> bool:
        """Validate incoming webhook secret header value."""
        configured = (self.config.webhook_secret or "").strip()
        if not configured:
            return True
        return secret == configured

    async def handle_webhook_update(self, update: dict[str, Any]) -> None:
        """Track latest update offset for polling fallback."""
        update_id = int(update.get("update_id", -1))
        if update_id >= 0:
            self.config.polling_offset = update_id + 1

    async def stream_draft_then_send(
        self,
        *,
        chat_id: Any,
        chunks: list[str],
        draft_id: int,
        delay_between_chunks: float = 0.0,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        """Stream intermediate draft updates then send final Telegram message."""
        if not self.client:
            raise TelegramAPIError(None, "Telegram client not initialized")
        if not chunks:
            return {}
        await self.client.send_chat_action(chat_id, "typing")
        for chunk in chunks[:-1]:
            await self.client.send_message_draft(chat_id=chat_id, draft_id=draft_id, text=chunk)
            if delay_between_chunks > 0:
                await asyncio.sleep(delay_between_chunks)
        return await self.client.send_message(chat_id=chat_id, text=chunks[-1], parse_mode=parse_mode)

    async def send_photo(self, chat_id: Any, image_b64: str) -> dict[str, Any]:
        """Send a base64-encoded PNG as a photo to a Telegram chat."""
        import base64, io
        url = f"{TELEGRAM_API_BASE}/bot{self._token}/sendPhoto"
        image_bytes = base64.b64decode(image_b64)
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                url,
                data={"chat_id": str(chat_id)},
                files={"photo": ("frame.png", io.BytesIO(image_bytes), "image/png")},
            )
        try:
            return response.json()
        except ValueError:
            return {"ok": False, "description": response.text}

    async def _request(
        self,
        method: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._token:
            return {"ok": False, "description": "Missing bot token"}

        url = f"{TELEGRAM_API_BASE}/bot{self._token}/{method}"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, params=params, json=json)

        try:
            data = response.json()
        except ValueError:
            data = {"ok": False, "description": response.text}

        if response.status_code >= 400 and isinstance(data, dict):
            data.setdefault("ok", False)
            data.setdefault("description", f"HTTP {response.status_code}")

        return data
