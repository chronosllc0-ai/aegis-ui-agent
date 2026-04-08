"""Telegram integration client using official Bot API methods."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
import io
import logging
from typing import Any

import httpx

from backend.integrations.text_normalization import normalize_for_channel
from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


@dataclass
class TelegramConfig:
    """Telegram integration runtime configuration."""

    bot_token: str
    webhook_secret: str = ""
    polling_offset: int = 0


@dataclass
class TelegramTelemetry:
    """In-memory compatibility telemetry for migration tracking."""

    deprecated_calls: dict[str, int] = field(default_factory=dict)

    def mark_deprecated(self, alias: str) -> None:
        self.deprecated_calls[alias] = self.deprecated_calls.get(alias, 0) + 1


class TelegramAPIError(RuntimeError):
    """Raised when the Telegram Bot API returns an error payload."""

    def __init__(self, error_code: int | None, description: str) -> None:
        super().__init__(description)
        self.error_code = error_code
        self.description = description


class TelegramClient:
    """Thin async Telegram Bot API client used by integration + tests."""

    def __init__(self, bot_token: str, telemetry: TelegramTelemetry | None = None) -> None:
        self._token = bot_token
        self._client = httpx.AsyncClient(timeout=10)
        self._telemetry = telemetry

    async def close(self) -> None:
        await self._client.aclose()

    async def _post(self, method: str, *, data: dict[str, Any] | None = None, json: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{TELEGRAM_API_BASE}/bot{self._token}/{method}"
        response = await self._client.post(url, data=data, json=json)
        payload = response.json()
        if not payload.get("ok"):
            raise TelegramAPIError(payload.get("error_code"), str(payload.get("description") or "Telegram API error"))
        return payload

    def _log_deprecated(self, alias: str, replacement: str) -> None:
        logger.warning("Deprecated Telegram pseudo-method `%s` used; mapping to `%s`.", alias, replacement)
        if self._telemetry:
            self._telemetry.mark_deprecated(alias)

    async def send_message(self, *, chat_id: Any, text: str, parse_mode: str | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode
        payload = await self._post("sendMessage", data=data)
        return payload.get("result", {})

    async def edit_message_text(
        self,
        *,
        chat_id: Any,
        message_id: int,
        text: str,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode
        payload = await self._post("editMessageText", data=data)
        return payload.get("result", {})

    async def send_message_draft(self, *, chat_id: Any, draft_id: int, text: str) -> bool:
        """Backward-compatible mapper for legacy sendMessageDraft usage."""
        if draft_id <= 0:
            raise ValueError("draft_id must be non-zero")
        self._log_deprecated("send_message_draft", "editMessageText")
        await self.edit_message_text(chat_id=chat_id, message_id=draft_id, text=text)
        return True

    async def set_chat_member_tag(self, *, chat_id: Any, user_id: Any, tag: str) -> bool:
        """Backward-compatible mapper for legacy setChatMemberTag usage."""
        self._log_deprecated("set_chat_member_tag", "setChatAdministratorCustomTitle")
        payload = await self._post(
            "setChatAdministratorCustomTitle",
            data={"chat_id": chat_id, "user_id": user_id, "custom_title": tag},
        )
        return bool(payload.get("result", True))

    async def send_chat_action(self, chat_id: Any, action: str) -> bool:
        payload = await self._post("sendChatAction", data={"chat_id": chat_id, "action": action})
        return bool(payload.get("result", True))

    async def _send_media(
        self,
        method: str,
        field_name: str,
        filename: str,
        mime_type: str,
        *,
        chat_id: Any,
        file_bytes: bytes,
        caption: str | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        files = {field_name: (filename, io.BytesIO(file_bytes), mime_type)}
        data: dict[str, Any] = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption
        if parse_mode:
            data["parse_mode"] = parse_mode
        url = f"{TELEGRAM_API_BASE}/bot{self._token}/{method}"
        response = await self._client.post(url, data=data, files=files)
        payload = response.json()
        if not payload.get("ok"):
            raise TelegramAPIError(payload.get("error_code"), str(payload.get("description") or "Telegram API error"))
        return payload.get("result", {})

    async def send_photo(self, *, chat_id: Any, image_bytes: bytes, caption: str | None = None, parse_mode: str | None = None) -> dict[str, Any]:
        return await self._send_media(
            "sendPhoto",
            "photo",
            "frame.png",
            "image/png",
            chat_id=chat_id,
            file_bytes=image_bytes,
            caption=caption,
            parse_mode=parse_mode,
        )

    async def send_document(
        self,
        *,
        chat_id: Any,
        file_bytes: bytes,
        filename: str = "file.bin",
        caption: str | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        return await self._send_media(
            "sendDocument",
            "document",
            filename,
            "application/octet-stream",
            chat_id=chat_id,
            file_bytes=file_bytes,
            caption=caption,
            parse_mode=parse_mode,
        )

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None, show_alert: bool = False) -> bool:
        data: dict[str, Any] = {"callback_query_id": callback_query_id, "show_alert": show_alert}
        if text:
            data["text"] = text
        payload = await self._post("answerCallbackQuery", data=data)
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
        self.telemetry = TelegramTelemetry()
        self.client: TelegramClient | None = TelegramClient(self._token, telemetry=self.telemetry) if self._token else None

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
            self.client = TelegramClient(self._token, telemetry=self.telemetry)

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
            self.config.polling_offset = 0
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
            self.config.polling_offset = 0

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
            {"name": "telegram_send_file", "description": "Send file data"},
            {"name": "telegram_list_chats", "description": "List chats"},
            {"name": "telegram_webhook_update", "description": "Handle inbound webhook update"},
        ]

    @staticmethod
    def mode_selector_reply_markup(mode_labels: dict[str, str]) -> dict[str, Any]:
        """Build a Telegram inline keyboard payload for mode selection."""
        return {
            "inline_keyboard": [
                [{"text": label, "callback_data": f"mode:{mode_name}"}]
                for mode_name, label in mode_labels.items()
            ]
        }

    @staticmethod
    def extract_mode_selection(callback_data: object) -> str | None:
        """Extract raw mode token from Telegram callback data."""
        data = str(callback_data or "").strip()
        if not data.startswith("mode:"):
            return None
        raw_mode = data[5:].strip().lower().replace("-", "_").replace(" ", "_")
        return raw_mode or None

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "telegram_webhook_update":
            return await self._handle_webhook_tool(params)

        if not self.connected or not self._token:
            return {"ok": False, "tool": tool_name, "error": "Telegram integration is not connected"}

        if tool_name == "telegram_list_chats":
            return await self._list_chats(params)
        if tool_name == "telegram_get_messages":
            return await self._get_messages(params)
        if tool_name == "telegram_send_message":
            return await self._send_message(params)
        if tool_name == "telegram_send_image":
            return await self._send_image(params)
        if tool_name == "telegram_send_file":
            return await self._send_file(params)

        return {"ok": False, "tool": tool_name, "error": "Unsupported tool"}

    async def _list_chats(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = int(params.get("limit", 20))
        data = await self._request("getUpdates", params={"limit": limit, "offset": self.config.polling_offset})
        return {"ok": bool(data.get("ok")), "tool": "telegram_list_chats", "result": data}

    async def _get_messages(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = int(params.get("limit", 20))
        offset = params.get("offset", self.config.polling_offset)
        payload: dict[str, Any] = {"limit": limit, "offset": offset}
        data = await self._request("getUpdates", params=payload)
        if data.get("ok"):
            for update in data.get("result", []):
                await self.handle_webhook_update(update)
        return {"ok": bool(data.get("ok")), "tool": "telegram_get_messages", "result": data}

    async def _send_message(self, params: dict[str, Any]) -> dict[str, Any]:
        chat_id = params.get("chat_id")
        text = str(params.get("text", "")).strip()
        parse_mode = str(params.get("parse_mode", "")).strip() or None
        reply_markup = params.get("reply_markup")
        if chat_id is None:
            return {"ok": False, "tool": "telegram_send_message", "error": "chat_id is required"}
        if not text:
            return {"ok": False, "tool": "telegram_send_message", "error": "Text is required"}
        if reply_markup is not None and not isinstance(reply_markup, dict):
            return {"ok": False, "tool": "telegram_send_message", "error": "reply_markup must be an object"}
        normalized_text, normalized_parse_mode = normalize_for_channel(text, channel="telegram", parse_mode=parse_mode)
        payload: dict[str, Any] = {"chat_id": chat_id, "text": normalized_text}
        if normalized_parse_mode:
            payload["parse_mode"] = normalized_parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        data = await self._request("sendMessage", json=payload)
        return {"ok": bool(data.get("ok")), "tool": "telegram_send_message", "result": data}

    async def _send_image(self, params: dict[str, Any]) -> dict[str, Any]:
        chat_id = params.get("chat_id")
        image_b64 = str(params.get("image_b64", "")).strip()
        caption = str(params.get("caption", "")).strip() or None
        parse_mode = str(params.get("parse_mode", "")).strip() or None
        if chat_id is None:
            return {"ok": False, "tool": "telegram_send_image", "error": "chat_id is required"}
        if not image_b64:
            return {"ok": False, "tool": "telegram_send_image", "error": "image_b64 is required"}
        try:
            image_bytes = base64.b64decode(image_b64, validate=True)
        except Exception:  # noqa: BLE001
            return {"ok": False, "tool": "telegram_send_image", "error": "image_b64 must be valid base64"}
        if not self.client:
            return {"ok": False, "tool": "telegram_send_image", "error": "Telegram client not initialized"}
        result = await self.client.send_photo(chat_id=chat_id, image_bytes=image_bytes, caption=caption, parse_mode=parse_mode)
        return {"ok": True, "tool": "telegram_send_image", "result": result}

    async def _send_file(self, params: dict[str, Any]) -> dict[str, Any]:
        chat_id = params.get("chat_id")
        file_b64 = str(params.get("file_b64", "")).strip()
        filename = str(params.get("filename", "file.bin")).strip() or "file.bin"
        caption = str(params.get("caption", "")).strip() or None
        parse_mode = str(params.get("parse_mode", "")).strip() or None
        if chat_id is None:
            return {"ok": False, "tool": "telegram_send_file", "error": "chat_id is required"}
        if not file_b64:
            return {"ok": False, "tool": "telegram_send_file", "error": "file_b64 is required"}
        try:
            file_bytes = base64.b64decode(file_b64, validate=True)
        except Exception:  # noqa: BLE001
            return {"ok": False, "tool": "telegram_send_file", "error": "file_b64 must be valid base64"}
        if not self.client:
            return {"ok": False, "tool": "telegram_send_file", "error": "Telegram client not initialized"}
        result = await self.client.send_document(
            chat_id=chat_id,
            file_bytes=file_bytes,
            filename=filename,
            caption=caption,
            parse_mode=parse_mode,
        )
        return {"ok": True, "tool": "telegram_send_file", "result": result}

    async def set_my_commands(self, commands: list[dict[str, str]]) -> dict[str, Any]:
        """Register slash commands with Telegram Bot API."""
        return await self._request("setMyCommands", json={"commands": commands})

    def validate_webhook_secret(self, secret: str) -> bool:
        """Validate incoming webhook secret header value."""
        configured = (self.config.webhook_secret or "").strip()
        if not configured:
            return True
        return secret == configured

    async def _handle_webhook_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        update = params.get("update") or {}
        if not isinstance(update, dict):
            return {"ok": False, "tool": "telegram_webhook_update", "error": "update must be an object"}

        await self.handle_webhook_update(update)
        callback = update.get("callback_query") or {}
        if callback and self.client:
            callback_id = str(callback.get("id", "")).strip()
            callback_data = str(callback.get("data", "")).strip()
            if callback_id:
                await self.client.answer_callback_query(callback_id, text="Received")
            action = self._parse_callback_action(callback_data)
            if action.get("type") == "edit":
                message = callback.get("message") or {}
                chat_id = (message.get("chat") or {}).get("id")
                message_id = message.get("message_id")
                if chat_id is not None and isinstance(message_id, int):
                    await self.client.edit_message_text(chat_id=chat_id, message_id=message_id, text=action.get("text", "Updated"))
            elif action.get("type") == "reply":
                message = callback.get("message") or {}
                chat_id = (message.get("chat") or {}).get("id")
                if chat_id is not None:
                    await self.client.send_message(chat_id=chat_id, text=action.get("text", "Done"))

        return {"ok": True, "tool": "telegram_webhook_update", "result": {"update_id": update.get("update_id")}}

    @staticmethod
    def _parse_callback_action(data: str) -> dict[str, str]:
        if data.startswith("edit:"):
            return {"type": "edit", "text": data[5:].strip() or "Updated"}
        if data.startswith("reply:"):
            return {"type": "reply", "text": data[6:].strip() or "Done"}
        return {"type": "none"}

    async def handle_webhook_update(self, update: dict[str, Any]) -> None:
        """Track latest update offset for polling fallback."""
        update_id = int(update.get("update_id", -1))
        if update_id >= 0:
            self.config.polling_offset = max(self.config.polling_offset, update_id + 1)

    async def stream_draft_then_send(
        self,
        *,
        chat_id: Any,
        chunks: list[str],
        draft_id: int,
        delay_between_chunks: float = 0.0,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        """Stream progressive updates using official send/edit APIs."""
        if not self.client:
            raise TelegramAPIError(None, "Telegram client not initialized")
        if not chunks:
            return {}
        await self.client.send_chat_action(chat_id, "typing")
        first_chunk, normalized_parse_mode = normalize_for_channel(chunks[0], channel="telegram", parse_mode=parse_mode)
        first = await self.client.send_message(chat_id=chat_id, text=first_chunk, parse_mode=normalized_parse_mode)
        message_id = int(first.get("message_id") or draft_id or 0)
        if message_id <= 0:
            raise TelegramAPIError(None, "Missing message_id for progressive updates")

        for chunk in chunks[1:]:
            normalized_chunk, _ = normalize_for_channel(chunk, channel="telegram", parse_mode=parse_mode)
            await self.client.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=normalized_chunk,
                parse_mode=normalized_parse_mode,
            )
            if delay_between_chunks > 0:
                await asyncio.sleep(delay_between_chunks)

        return {"message_id": message_id}

    async def send_photo(
        self,
        chat_id: Any,
        image_b64: str,
        caption: str | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        """Send a base64-encoded PNG as a photo to a Telegram chat."""
        if not self.client:
            raise TelegramAPIError(None, "Telegram client not initialized")
        image_bytes = base64.b64decode(image_b64, validate=True)
        return await self.client.send_photo(chat_id=chat_id, image_bytes=image_bytes, caption=caption, parse_mode=parse_mode)

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
