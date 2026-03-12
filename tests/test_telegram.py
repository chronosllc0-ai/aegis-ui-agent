"""Telegram Bot API 9.5 integration tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from integrations.telegram import TelegramAPIError, TelegramClient, TelegramConfig, TelegramIntegration


def test_send_message_draft_request() -> None:
    """Verify sendMessageDraft sends POST to correct URL with correct params."""

    async def run() -> None:
        client = TelegramClient("123:ABC")
        with patch.object(client._client, "post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={"ok": True, "result": True})
            result = await client.send_message_draft(chat_id=12345, draft_id=1, text="Partial response...")
            assert result is True
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "sendMessageDraft" in str(call_args)
            assert call_args[1]["data"]["chat_id"] == 12345
            assert call_args[1]["data"]["draft_id"] == 1
            assert call_args[1]["data"]["text"] == "Partial response..."
        await client.close()

    asyncio.run(run())


def test_send_message_draft_zero_draft_id() -> None:
    """Telegram requires draft_id to be non-zero."""

    async def run() -> None:
        client = TelegramClient("123:ABC")
        with pytest.raises(ValueError):
            await client.send_message_draft(chat_id=1, draft_id=0, text="x")
        await client.close()

    asyncio.run(run())


def test_set_chat_member_tag() -> None:
    """Verify setChatMemberTag sends correct params."""

    async def run() -> None:
        client = TelegramClient("123:ABC")
        with patch.object(client._client, "post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={"ok": True, "result": True})
            result = await client.set_chat_member_tag(chat_id=-100123456, user_id=789, tag="VIP")
            assert result is True
            call_args = mock_post.call_args
            assert "setChatMemberTag" in str(call_args)
        await client.close()

    asyncio.run(run())


def test_webhook_secret_validation() -> None:
    config = TelegramConfig(bot_token="123:ABC", webhook_secret="my-secret-123")
    integration = TelegramIntegration(config)
    assert integration.validate_webhook_secret("my-secret-123") is True
    assert integration.validate_webhook_secret("wrong-secret") is False
    assert integration.validate_webhook_secret("") is False


def test_webhook_secret_validation_no_secret() -> None:
    config = TelegramConfig(bot_token="123:ABC", webhook_secret="")
    integration = TelegramIntegration(config)
    assert integration.validate_webhook_secret("") is True
    assert integration.validate_webhook_secret("anything") is True


def test_polling_offset_updates() -> None:
    async def run() -> None:
        config = TelegramConfig(bot_token="123:ABC")
        integration = TelegramIntegration(config)
        assert config.polling_offset == 0
        await integration.handle_webhook_update({"update_id": 42})
        assert config.polling_offset == 43
        await integration.disconnect()

    asyncio.run(run())


def test_stream_draft_then_send() -> None:
    async def run() -> None:
        config = TelegramConfig(bot_token="123:ABC")
        integration = TelegramIntegration(config)
        assert integration.client is not None
        with patch.object(integration.client, "send_chat_action", new_callable=AsyncMock) as mock_action, patch.object(
            integration.client,
            "send_message_draft",
            new_callable=AsyncMock,
        ) as mock_draft, patch.object(integration.client, "send_message", new_callable=AsyncMock) as mock_send:
            mock_draft.return_value = True
            mock_send.return_value = {"message_id": 1}
            mock_action.return_value = True

            result = await integration.stream_draft_then_send(
                chat_id=12345,
                chunks=["Thinking...", "Thinking... found data", "Here are your results: ..."],
                draft_id=1,
                delay_between_chunks=0.01,
            )

            mock_action.assert_called_once_with(12345, "typing")
            assert mock_draft.call_count == 2
            mock_send.assert_called_once_with(chat_id=12345, text="Here are your results: ...", parse_mode=None)
            assert result == {"message_id": 1}
        await integration.disconnect()

    asyncio.run(run())


def test_api_error_handling() -> None:
    async def run() -> None:
        client = TelegramClient("123:ABC")
        with patch.object(client._client, "post") as mock_post:
            mock_post.return_value = httpx.Response(
                200,
                json={"ok": False, "error_code": 400, "description": "Bad Request: chat not found"},
            )
            with pytest.raises(TelegramAPIError) as exc_info:
                await client.send_message(chat_id=99999, text="test")
            assert exc_info.value.error_code == 400
            assert "chat not found" in exc_info.value.description
        await client.close()

    asyncio.run(run())
