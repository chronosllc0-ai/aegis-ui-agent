"""Regression coverage for channel runtime adapters."""

from __future__ import annotations

from backend.integrations.channel_runtime import DiscordChannelAdapter, TelegramChannelAdapter


class _StubIntegration:
    async def execute_tool(self, name: str, payload: dict[str, object]) -> dict[str, object]:
        return {"tool": name, "payload": payload}


def test_telegram_adapter_preserves_none_callback_data() -> None:
    adapter = TelegramChannelAdapter(_StubIntegration())

    inbound = adapter.extract_message(
        {
            "callback_query": {
                "data": None,
                "message": {"chat": {"id": 123}, "message_id": 456},
            }
        }
    )

    assert inbound.destination == "123"
    assert inbound.text is None
    assert inbound.message_id == "456"


def test_telegram_adapter_preserves_none_message_text() -> None:
    adapter = TelegramChannelAdapter(_StubIntegration())

    inbound = adapter.extract_message(
        {
            "message": {
                "chat": {"id": 321},
                "text": None,
                "message_id": 654,
            }
        }
    )

    assert inbound.destination == "321"
    assert inbound.text is None
    assert inbound.message_id == "654"


def test_discord_adapter_does_not_stringify_none_text_values() -> None:
    adapter = DiscordChannelAdapter(_StubIntegration())

    inbound = adapter.extract_message(
        {
            "channel_id": "chan-1",
            "message": {"id": "msg-1"},
            "data": {"text": None, "options": [{"value": None}]},
            "content": None,
        }
    )

    assert inbound.destination == "chan-1"
    assert inbound.text is None
    assert inbound.message_id == "msg-1"
