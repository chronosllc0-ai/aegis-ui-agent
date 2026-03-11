"""Real Telegram Bot API 9.5 integration."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


@dataclass
class TelegramConfig:
    """Telegram integration configuration."""

    bot_token: str
    delivery_mode: str = "polling"
    webhook_url: str = ""
    webhook_secret: str = ""
    allowed_updates: list[str] = field(default_factory=lambda: ["message", "callback_query"])
    polling_interval: float = 1.0
    polling_offset: int = 0


class TelegramAPIError(Exception):
    """Raised when Telegram returns ok: false."""

    def __init__(self, error_code: int, description: str):
        self.error_code = error_code
        self.description = description
        super().__init__(f"[{error_code}] {description}")


class TelegramClient:
    """Async Telegram Bot API 9.5 client using raw HTTP calls."""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self._client = httpx.AsyncClient(timeout=30.0)

    def _url(self, method: str) -> str:
        return TELEGRAM_API_BASE.format(token=self.bot_token, method=method)

    async def _request(self, method: str, **params) -> dict[str, Any] | list[dict[str, Any]] | bool:
        """Make a request to the Telegram Bot API."""
        payload = {k: v for k, v in params.items() if v is not None}

        for key, value in payload.items():
            if isinstance(value, (list, dict)):
                payload[key] = json.dumps(value)

        response = await self._client.post(self._url(method), data=payload)
        result = response.json()

        if not result.get("ok"):
            error_code = result.get("error_code", 0)
            description = result.get("description", "Unknown error")
            logger.error("Telegram API error: [%s] %s", error_code, description)
            raise TelegramAPIError(error_code, description)

        return result.get("result")

    async def get_me(self) -> dict[str, Any]:
        return await self._request("getMe")  # type: ignore[return-value]

    async def get_webhook_info(self) -> dict[str, Any]:
        return await self._request("getWebhookInfo")  # type: ignore[return-value]

    async def set_webhook(
        self,
        url: str,
        secret_token: str | None = None,
        allowed_updates: list[str] | None = None,
        max_connections: int | None = None,
        drop_pending_updates: bool | None = None,
    ) -> bool:
        return await self._request(
            "setWebhook",
            url=url,
            secret_token=secret_token,
            allowed_updates=allowed_updates,
            max_connections=max_connections,
            drop_pending_updates=drop_pending_updates,
        )  # type: ignore[return-value]

    async def delete_webhook(self, drop_pending_updates: bool = False) -> bool:
        return await self._request("deleteWebhook", drop_pending_updates=drop_pending_updates)  # type: ignore[return-value]

    async def get_updates(
        self,
        offset: int | None = None,
        limit: int = 100,
        timeout: int = 30,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        return await self._request(
            "getUpdates",
            offset=offset,
            limit=limit,
            timeout=timeout,
            allowed_updates=allowed_updates,
        )  # type: ignore[return-value]

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        entities: list[dict[str, Any]] | None = None,
        message_thread_id: int | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            entities=entities,
            message_thread_id=message_thread_id,
            reply_to_message_id=reply_to_message_id,
        )  # type: ignore[return-value]

    async def send_message_draft(
        self,
        chat_id: int,
        draft_id: int,
        text: str,
        message_thread_id: int | None = None,
        parse_mode: str | None = None,
        entities: list[dict[str, Any]] | None = None,
    ) -> bool:
        if draft_id == 0:
            raise ValueError("draft_id must be non-zero")
        return await self._request(
            "sendMessageDraft",
            chat_id=chat_id,
            draft_id=draft_id,
            text=text,
            message_thread_id=message_thread_id,
            parse_mode=parse_mode,
            entities=entities,
        )  # type: ignore[return-value]

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> bool:
        return await self._request("sendChatAction", chat_id=chat_id, action=action)  # type: ignore[return-value]

    async def set_chat_member_tag(self, chat_id: int | str, user_id: int, tag: str | None = None) -> bool:
        return await self._request("setChatMemberTag", chat_id=chat_id, user_id=user_id, tag=tag)  # type: ignore[return-value]

    async def close(self):
        await self._client.aclose()


class TelegramIntegration(BaseIntegration):
    """Full Telegram integration for Aegis with webhook + polling support."""

    name = "telegram"

    def __init__(self, config: TelegramConfig | None = None):
        self.config = config or TelegramConfig(bot_token="")
        self.client: TelegramClient | None = TelegramClient(self.config.bot_token) if self.config.bot_token else None
        self._polling_task: asyncio.Task[None] | None = None

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        self.config = TelegramConfig(
            bot_token=str(config.get("bot_token", "")).strip(),
            delivery_mode=str(config.get("delivery_mode", "polling")),
            webhook_url=str(config.get("webhook_url", "")),
            webhook_secret=str(config.get("webhook_secret", "")),
            allowed_updates=list(config.get("allowed_updates", ["message", "callback_query"])),
            polling_interval=float(config.get("polling_interval", 1.0)),
            polling_offset=int(config.get("polling_offset", 0)),
        )
        self.client = TelegramClient(self.config.bot_token)
        me = await self.connect_identity()
        return {"connected": True, "bot": me, "delivery_mode": self.config.delivery_mode}

    async def connect_identity(self) -> dict[str, Any]:
        if self.client is None:
            raise ValueError("Telegram client is not configured")
        me = await self.client.get_me()
        logger.info("Telegram bot connected: @%s (id: %s)", me.get("username"), me.get("id"))
        return me

    async def test(self) -> dict[str, Any]:
        if self.client is None:
            raise ValueError("Telegram client is not configured")
        me = await self.client.get_me()
        webhook_info = await self.client.get_webhook_info()
        return {"bot": me, "webhook": webhook_info, "delivery_mode": self.config.delivery_mode}

    async def setup_webhook(self, url: str, secret: str | None = None) -> bool:
        if self.client is None:
            raise ValueError("Telegram client is not configured")
        if not url.startswith("https://"):
            raise ValueError("Telegram webhook URL must be HTTPS")
        self.config.webhook_url = url
        if secret is not None:
            self.config.webhook_secret = secret
        return await self.client.set_webhook(url=url, secret_token=secret, allowed_updates=self.config.allowed_updates)

    async def start_polling(self, handler):
        if self.client is None:
            raise ValueError("Telegram client is not configured")
        self.config.delivery_mode = "polling"
        await self.client.delete_webhook(drop_pending_updates=True)

        async def poll_loop() -> None:
            offset = self.config.polling_offset
            while True:
                try:
                    updates = await self.client.get_updates(
                        offset=offset,
                        timeout=30,
                        allowed_updates=self.config.allowed_updates,
                    )
                    for update in updates:
                        offset = update["update_id"] + 1
                        self.config.polling_offset = offset
                        await handler(update)
                except httpx.ReadTimeout:
                    continue
                except Exception as exc:  # noqa: BLE001
                    logger.error("Polling error: %s", exc)
                    await asyncio.sleep(self.config.polling_interval)

        self._polling_task = asyncio.create_task(poll_loop())
        logger.info("Telegram polling started")

    async def stop_polling(self):
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None
            logger.info("Telegram polling stopped")

    def validate_webhook_secret(self, request_secret: str) -> bool:
        if not self.config.webhook_secret:
            return True
        return request_secret == self.config.webhook_secret

    async def stream_draft_then_send(
        self,
        chat_id: int,
        chunks: list[str],
        draft_id: int = 1,
        delay_between_chunks: float = 0.3,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        if self.client is None:
            raise ValueError("Telegram client is not configured")
        if not chunks:
            raise ValueError("chunks must not be empty")

        await self.client.send_chat_action(chat_id, "typing")
        for chunk in chunks[:-1]:
            await self.client.send_message_draft(
                chat_id=chat_id,
                draft_id=draft_id,
                text=chunk,
                parse_mode=parse_mode,
            )
            await asyncio.sleep(delay_between_chunks)

        final_text = chunks[-1]
        result = await self.client.send_message(chat_id=chat_id, text=final_text, parse_mode=parse_mode)
        return result

    async def handle_webhook_update(self, update: dict[str, Any]) -> None:
        """Handle a webhook update payload."""
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            self.config.polling_offset = max(self.config.polling_offset, update_id + 1)

    def get_tool_manifest(self) -> list[dict[str, Any]]:
        return [
            {"name": "telegram_get_me", "description": "Get the bot's identity and username"},
            {"name": "telegram_send_message", "description": "Send a message to a Telegram chat", "parameters": {"chat_id": "int", "text": "str"}},
            {"name": "telegram_send_message_draft", "description": "Bot API 9.5 partial message draft updates", "parameters": {"chat_id": "int", "draft_id": "int", "text": "str"}},
            {"name": "telegram_send_chat_action", "description": "Send a typing indicator", "parameters": {"chat_id": "int", "action": "str"}},
            {"name": "telegram_set_chat_member_tag", "description": "Bot API 9.5 member tag", "parameters": {"chat_id": "int|str", "user_id": "int", "tag": "str"}},
            {"name": "telegram_get_webhook_info", "description": "Get webhook health"},
        ]

    def list_tools(self) -> list[dict[str, Any]]:
        return self.get_tool_manifest()

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.client is None:
            raise ValueError("Telegram client is not configured")
        if tool_name == "telegram_get_me":
            return await self.client.get_me()
        if tool_name == "telegram_send_message":
            return await self.client.send_message(**params)
        if tool_name == "telegram_send_message_draft":
            result = await self.client.send_message_draft(**params)
            return {"ok": result}
        if tool_name == "telegram_send_chat_action":
            result = await self.client.send_chat_action(**params)
            return {"ok": result}
        if tool_name == "telegram_set_chat_member_tag":
            result = await self.client.set_chat_member_tag(**params)
            return {"ok": result}
        if tool_name == "telegram_get_webhook_info":
            return await self.client.get_webhook_info()
        raise ValueError(f"Unknown tool: {tool_name}")

    async def disconnect(self):
        await self.stop_polling()
        if self.client is not None:
            await self.client.close()
            self.client = None
