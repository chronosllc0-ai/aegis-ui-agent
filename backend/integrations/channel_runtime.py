"""Unified runtime adapter layer for channel-based integrations."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Literal

from integrations.discord import DiscordIntegration
from integrations.slack_connector import SlackIntegration
from integrations.telegram import TelegramIntegration

ChannelPlatform = Literal["telegram", "slack", "discord"]


def _coerce_optional_text(value: Any) -> str | None:
    """Return stripped text while preserving None values."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(slots=True)
class InboundChannelMessage:
    """Canonical inbound channel message envelope."""

    destination: str | None
    text: str | None
    message_id: str | None


class TelegramChannelAdapter:
    """Channel-runtime adapter for Telegram."""

    platform: ChannelPlatform = "telegram"

    def __init__(self, integration: TelegramIntegration) -> None:
        self.integration = integration

    async def handle_event(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        _ = headers
        return await self.integration.execute_tool("telegram_webhook_update", {"update": payload})

    def extract_mode_selection(self, payload: dict[str, Any]) -> str | None:
        callback = payload.get("callback_query") or {}
        return TelegramIntegration.extract_mode_selection(callback_data=callback.get("data"))

    def extract_reasoning_selection(self, payload: dict[str, Any]) -> str | None:
        callback = payload.get("callback_query") or {}
        return TelegramIntegration.extract_reasoning_selection(callback_data=callback.get("data"))

    def extract_message(self, payload: dict[str, Any]) -> InboundChannelMessage:
        callback_query = payload.get("callback_query") or {}
        if callback_query:
            message = callback_query.get("message") or {}
            chat_id = (message.get("chat") or {}).get("id")
            text = _coerce_optional_text(callback_query.get("data"))
            message_id = message.get("message_id")
            return InboundChannelMessage(
                destination=str(chat_id) if chat_id is not None else None,
                text=text,
                message_id=str(message_id) if message_id is not None else None,
            )

        message = payload.get("message") or payload.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = _coerce_optional_text(message.get("text"))
        message_id = message.get("message_id")
        return InboundChannelMessage(
            destination=str(chat_id) if chat_id is not None else None,
            text=text,
            message_id=str(message_id) if message_id is not None else None,
        )

    async def send_text(self, destination: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": destination, "text": text}
        metadata = metadata or {}
        if metadata.get("parse_mode"):
            payload["parse_mode"] = metadata["parse_mode"]
        if isinstance(metadata.get("reply_markup"), dict):
            payload["reply_markup"] = metadata["reply_markup"]
        if metadata.get("draft"):
            payload["draft"] = True
        return await self.integration.execute_tool("telegram_send_message", payload)

    async def test_connection(self) -> dict[str, Any]:
        return await self.integration.execute_tool("telegram_list_chats", {})


class SlackChannelAdapter:
    """Channel-runtime adapter for Slack."""

    platform: ChannelPlatform = "slack"

    def __init__(self, integration: SlackIntegration) -> None:
        self.integration = integration

    async def handle_event(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        return await self.integration.execute_tool("slack_handle_event", {"payload": payload, "headers": headers})

    def extract_mode_selection(self, payload: dict[str, Any]) -> str | None:
        return SlackIntegration.extract_mode_selection(payload)

    def extract_reasoning_selection(self, payload: dict[str, Any]) -> str | None:
        return SlackIntegration.extract_reasoning_selection(payload)

    def extract_message(self, payload: dict[str, Any]) -> InboundChannelMessage:
        event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
        channel = event.get("channel") or payload.get("channel_id")
        text = event.get("text") or payload.get("text")
        message_id = event.get("ts") or payload.get("message_ts")
        return InboundChannelMessage(
            destination=str(channel) if channel is not None and str(channel).strip() else None,
            text=str(text).strip() if text is not None and str(text).strip() else None,
            message_id=str(message_id) if message_id is not None and str(message_id).strip() else None,
        )

    async def send_text(self, destination: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        send_text = getattr(self.integration, "send_text", None)
        if callable(send_text):
            return await send_text(destination, text, metadata=metadata)
        return await self.integration.execute_tool(
            "slack_send_message",
            {"channel": destination, "text": text, **(metadata or {})},
        )

    async def test_connection(self) -> dict[str, Any]:
        return await self.integration.execute_tool("slack_list_channels", {})


class DiscordChannelAdapter:
    """Channel-runtime adapter for Discord."""

    platform: ChannelPlatform = "discord"

    def __init__(self, integration: DiscordIntegration) -> None:
        self.integration = integration

    async def handle_event(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        return await self.integration.execute_tool("discord_handle_event", {"payload": payload, "headers": headers})

    def extract_mode_selection(self, payload: dict[str, Any]) -> str | None:
        return DiscordIntegration.extract_mode_selection(payload)

    def extract_reasoning_selection(self, payload: dict[str, Any]) -> str | None:
        return DiscordIntegration.extract_reasoning_selection(payload)

    def extract_message(self, payload: dict[str, Any]) -> InboundChannelMessage:
        channel = payload.get("channel_id")
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        options = data.get("options") if isinstance(data.get("options"), list) else []
        option_value = None
        if options and isinstance(options[0], dict):
            option_value = _coerce_optional_text(options[0].get("value"))
        text = option_value or _coerce_optional_text(data.get("text")) or _coerce_optional_text(payload.get("content"))
        message_id = message.get("id") or payload.get("id")
        return InboundChannelMessage(
            destination=str(channel) if channel is not None and str(channel).strip() else None,
            text=text or None,
            message_id=str(message_id) if message_id is not None and str(message_id).strip() else None,
        )

    async def send_text(self, destination: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        send_text = getattr(self.integration, "send_text", None)
        if callable(send_text):
            return await send_text(destination, text, metadata=metadata)
        return await self.integration.execute_tool(
            "discord_send_message",
            {"channel_id": destination, "content": text, **(metadata or {})},
        )

    async def test_connection(self) -> dict[str, Any]:
        return await self.integration.execute_tool("discord_list_channels", {})


@dataclass(slots=True)
class ChannelRuntimeEntry:
    """Connected runtime adapter + config pair."""

    platform: ChannelPlatform
    adapter: TelegramChannelAdapter | SlackChannelAdapter | DiscordChannelAdapter
    config: dict[str, Any]


class ChannelRuntimeRegistry:
    """Unified registry for channel runtime adapters."""

    def __init__(self) -> None:
        self._entries: dict[str, ChannelRuntimeEntry] = {}

    @staticmethod
    def _key(platform: str, integration_id: str) -> str:
        return f"{platform}:{integration_id}"

    def upsert(
        self,
        platform: ChannelPlatform,
        integration_id: str,
        adapter: TelegramChannelAdapter | SlackChannelAdapter | DiscordChannelAdapter,
        config: dict[str, Any],
    ) -> None:
        self._entries[self._key(platform, integration_id)] = ChannelRuntimeEntry(
            platform=platform,
            adapter=adapter,
            config=config,
        )

    def get_entry(self, platform: str, integration_id: str) -> ChannelRuntimeEntry | None:
        return self._entries.get(self._key(platform, integration_id))

    def get_adapter(self, platform: str, integration_id: str) -> TelegramChannelAdapter | SlackChannelAdapter | DiscordChannelAdapter | None:
        entry = self.get_entry(platform, integration_id)
        return entry.adapter if entry else None

    def get_config(self, platform: str, integration_id: str) -> dict[str, Any]:
        entry = self.get_entry(platform, integration_id)
        return dict(entry.config) if entry else {}

    def get_integration(self, platform: str, integration_id: str) -> TelegramIntegration | SlackIntegration | DiscordIntegration | None:
        entry = self.get_entry(platform, integration_id)
        if entry is None:
            return None
        return entry.adapter.integration


def encode_file_for_channel(file_bytes: bytes) -> str:
    """Encode raw bytes for channels whose send-file APIs expect base64 payloads."""

    return base64.b64encode(file_bytes).decode("ascii")
