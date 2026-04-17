"""Telegram integration conformance tests for official Bot API patterns."""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from integrations.telegram import TelegramAPIError, TelegramClient, TelegramConfig, TelegramIntegration


def test_legacy_send_message_draft_maps_to_edit_message_text() -> None:
    """Legacy send_message_draft alias should map to editMessageText."""

    async def run() -> None:
        telemetry_calls: list[str] = []

        class _Telemetry:
            def mark_deprecated(self, alias: str) -> None:
                telemetry_calls.append(alias)

        client = TelegramClient("123:ABC", telemetry=_Telemetry())
        with patch.object(client, "edit_message_text", new_callable=AsyncMock) as mock_edit:
            mock_edit.return_value = {"message_id": 55}
            result = await client.send_message_draft(chat_id=12345, draft_id=55, text="Partial response...")
            assert result is True
            mock_edit.assert_called_once_with(chat_id=12345, message_id=55, text="Partial response...")
            assert telemetry_calls == ["send_message_draft"]
        await client.close()

    asyncio.run(run())


def test_legacy_send_message_draft_zero_draft_id() -> None:
    """Legacy draft_id is still validated during migration."""

    async def run() -> None:
        client = TelegramClient("123:ABC")
        with pytest.raises(ValueError):
            await client.send_message_draft(chat_id=1, draft_id=0, text="x")
        await client.close()

    asyncio.run(run())


def test_legacy_set_chat_member_tag_maps_to_custom_title() -> None:
    """Legacy set_chat_member_tag alias should map to official custom title API."""

    async def run() -> None:
        telemetry_calls: list[str] = []

        class _Telemetry:
            def mark_deprecated(self, alias: str) -> None:
                telemetry_calls.append(alias)

        client = TelegramClient("123:ABC", telemetry=_Telemetry())
        with patch.object(client._client, "post") as mock_post:
            mock_post.return_value = httpx.Response(200, json={"ok": True, "result": True})
            result = await client.set_chat_member_tag(chat_id=-100123456, user_id=789, tag="VIP")
            assert result is True
            call_args = mock_post.call_args
            assert "setChatAdministratorCustomTitle" in str(call_args)
            assert telemetry_calls == ["set_chat_member_tag"]
        await client.close()

    asyncio.run(run())


def test_set_my_commands_success_and_failure() -> None:
    """setMyCommands should pass shape and surface API success/failure."""

    async def run() -> None:
        integration = TelegramIntegration(TelegramConfig(bot_token="123:ABC"))
        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"ok": True, "result": True}
            payload = [{"command": "run", "description": "Run"}]
            result = await integration.set_my_commands(payload)
            assert result["ok"] is True
            mock_request.assert_awaited_once_with("setMyCommands", json={"commands": payload})

        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"ok": False, "description": "Bad Request"}
            payload = [{"command": "run", "description": "Run"}]
            result = await integration.set_my_commands(payload)
            assert result["ok"] is False
        await integration.disconnect()

    asyncio.run(run())


def test_webhook_callback_answers_and_edits_message() -> None:
    """Callback query flow should answer callback and support edit actions."""

    async def run() -> None:
        integration = TelegramIntegration(TelegramConfig(bot_token="123:ABC"))
        integration.connected = True
        assert integration.client is not None
        with patch.object(integration.client, "answer_callback_query", new_callable=AsyncMock) as mock_answer, patch.object(
            integration.client,
            "edit_message_text",
            new_callable=AsyncMock,
        ) as mock_edit:
            result = await integration.execute_tool(
                "telegram_webhook_update",
                {
                    "update": {
                        "update_id": 99,
                        "callback_query": {
                            "id": "cb-1",
                            "data": "edit:Updated from callback",
                            "message": {"message_id": 7, "chat": {"id": 12345}},
                        },
                    }
                },
            )
            assert result["ok"] is True
            mock_answer.assert_awaited_once_with("cb-1", text="Received")
            mock_edit.assert_awaited_once_with(chat_id=12345, message_id=7, text="Updated from callback")
            assert integration.config.polling_offset == 100
        await integration.disconnect()

    asyncio.run(run())


def test_stream_draft_then_send_uses_edit_api() -> None:
    """Progressive response should use sendMessage + editMessageText path."""

    async def run() -> None:
        integration = TelegramIntegration(TelegramConfig(bot_token="123:ABC"))
        assert integration.client is not None
        with patch.object(integration.client, "send_chat_action", new_callable=AsyncMock) as mock_action, patch.object(
            integration.client,
            "send_message",
            new_callable=AsyncMock,
        ) as mock_send, patch.object(integration.client, "edit_message_text", new_callable=AsyncMock) as mock_edit:
            mock_send.return_value = {"message_id": 33}
            mock_edit.return_value = {"message_id": 33}
            mock_action.return_value = True

            result = await integration.stream_draft_then_send(
                chat_id=12345,
                chunks=["Thinking...", "Thinking... found data", "Here are your results: ..."],
                draft_id=1,
                delay_between_chunks=0.01,
                parse_mode="MarkdownV2",
            )

            mock_action.assert_called_once_with(12345, "typing")
            mock_send.assert_called_once_with(chat_id=12345, text="Thinking\\.\\.\\.", parse_mode="MarkdownV2")
            assert mock_edit.call_count == 2
            for call in mock_edit.await_args_list:
                assert call.kwargs["parse_mode"] == "MarkdownV2"
            assert result == {"message_id": 33}
        await integration.disconnect()

    asyncio.run(run())


def test_telegram_send_image_success_and_validation_errors() -> None:
    """telegram_send_image should validate inputs and call sendPhoto path."""

    async def run() -> None:
        integration = TelegramIntegration(TelegramConfig(bot_token="123:ABC"))
        integration.connected = True
        assert integration.client is not None

        missing_chat = await integration.execute_tool(
            "telegram_send_image",
            {"image_b64": base64.b64encode(b"png").decode("utf-8")},
        )
        assert missing_chat["ok"] is False

        invalid_b64 = await integration.execute_tool("telegram_send_image", {"chat_id": 1, "image_b64": "not-base64"})
        assert invalid_b64["ok"] is False

        with patch.object(integration.client, "send_photo", new_callable=AsyncMock) as mock_send_photo:
            mock_send_photo.return_value = {"message_id": 42}
            ok_result = await integration.execute_tool(
                "telegram_send_image",
                {
                    "chat_id": 1,
                    "image_b64": base64.b64encode(b"png").decode("utf-8"),
                    "caption": "frame",
                    "parse_mode": "Markdown",
                },
            )
            assert ok_result["ok"] is True
            assert ok_result["tool"] == "telegram_send_image"
            mock_send_photo.assert_awaited_once()
        await integration.disconnect()

    asyncio.run(run())


def test_telegram_core_tools_send_file_edit_delete_react() -> None:
    """Core Telegram tool handlers should call official client APIs."""

    async def run() -> None:
        integration = TelegramIntegration(TelegramConfig(bot_token="123:ABC"))
        integration.connected = True
        assert integration.client is not None

        with patch.object(integration.client, "send_document", new_callable=AsyncMock) as mock_send_document, patch.object(
            integration.client,
            "edit_message_text",
            new_callable=AsyncMock,
        ) as mock_edit, patch.object(integration.client, "delete_message", new_callable=AsyncMock) as mock_delete, patch.object(
            integration.client,
            "set_message_reaction",
            new_callable=AsyncMock,
        ) as mock_react:
            mock_send_document.return_value = {"message_id": 8}
            mock_edit.return_value = {"message_id": 8}
            mock_delete.return_value = True
            mock_react.return_value = True

            file_result = await integration.execute_tool(
                "telegram_send_file",
                {"chat_id": 1, "file_b64": base64.b64encode(b"data").decode("utf-8"), "filename": "a.txt"},
            )
            assert file_result["ok"] is True

            edit_result = await integration.execute_tool(
                "telegram_edit_message",
                {"chat_id": 1, "message_id": 8, "text": "updated"},
            )
            assert edit_result["ok"] is True

            delete_result = await integration.execute_tool(
                "telegram_delete_message",
                {"chat_id": 1, "message_id": 8},
            )
            assert delete_result["ok"] is True

            react_result = await integration.execute_tool(
                "telegram_react",
                {"chat_id": 1, "message_id": 8, "reaction": "👍"},
            )
            assert react_result["ok"] is True

            mock_send_document.assert_awaited_once()
            mock_edit.assert_awaited_once()
            mock_delete.assert_awaited_once()
            mock_react.assert_awaited_once()

        await integration.disconnect()

    asyncio.run(run())


def test_telegram_poll_topic_and_interactive_tools() -> None:
    """Poll/topic/interactive handlers should be functional end-to-end."""

    async def run() -> None:
        integration = TelegramIntegration(TelegramConfig(bot_token="123:ABC"))
        integration.connected = True
        assert integration.client is not None
        with patch.object(integration.client, "send_poll", new_callable=AsyncMock) as mock_poll, patch.object(
            integration.client,
            "create_forum_topic",
            new_callable=AsyncMock,
        ) as mock_topic_create, patch.object(integration.client, "edit_forum_topic", new_callable=AsyncMock) as mock_topic_edit, patch.object(
            integration,
            "_request",
            new_callable=AsyncMock,
        ) as mock_request:
            mock_poll.return_value = {"id": "poll-1"}
            mock_topic_create.return_value = {"message_thread_id": 99, "name": "Ops"}
            mock_topic_edit.return_value = True
            mock_request.return_value = {"ok": True, "result": {"message_id": 17}}

            poll_result = await integration.execute_tool(
                "telegram_send_poll",
                {"chat_id": 1, "question": "Ship today?", "options": ["Yes", "No"]},
            )
            assert poll_result["ok"] is True

            topic_create_result = await integration.execute_tool(
                "telegram_topic_create",
                {"chat_id": -1001, "name": "Ops"},
            )
            assert topic_create_result["ok"] is True

            topic_edit_result = await integration.execute_tool(
                "telegram_topic_edit",
                {"chat_id": -1001, "message_thread_id": 99, "name": "Ops - Priority"},
            )
            assert topic_edit_result["ok"] is True

            interactive_result = await integration.execute_tool(
                "telegram_send_interactive",
                {
                    "chat_id": 1,
                    "text": "Choose",
                    "buttons": [[{"text": "Go", "callback_data": "reply:done"}]],
                },
            )
            assert interactive_result["ok"] is True
            sent_payload = mock_request.await_args.kwargs["json"]
            assert sent_payload["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "reply:done"

        await integration.disconnect()

    asyncio.run(run())


def test_polling_path_processes_callback_query() -> None:
    """getUpdates polling should execute callback_query handling path."""

    async def run() -> None:
        integration = TelegramIntegration(TelegramConfig(bot_token="123:ABC"))
        integration.connected = True
        assert integration.client is not None
        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request, patch.object(
            integration.client,
            "answer_callback_query",
            new_callable=AsyncMock,
        ) as mock_answer, patch.object(integration.client, "edit_message_text", new_callable=AsyncMock) as mock_edit:
            mock_request.return_value = {
                "ok": True,
                "result": [
                    {
                        "update_id": 111,
                        "callback_query": {
                            "id": "cb-1",
                            "data": "edit:patched",
                            "message": {"message_id": 22, "chat": {"id": 5}},
                        },
                    }
                ],
            }
            result = await integration.execute_tool("telegram_get_messages", {"limit": 1})
            assert result["ok"] is True
            mock_answer.assert_awaited_once_with("cb-1", text="Received")
            mock_edit.assert_awaited_once_with(chat_id=5, message_id=22, text="patched")
            assert integration.config.polling_offset == 112
        await integration.disconnect()

    asyncio.run(run())


def test_unknown_callback_action_reports_unhandled() -> None:
    """Unknown callback payload should not be marked as handled."""

    async def run() -> None:
        integration = TelegramIntegration(TelegramConfig(bot_token="123:ABC"))
        integration.connected = True
        assert integration.client is not None
        with patch.object(integration.client, "answer_callback_query", new_callable=AsyncMock) as mock_answer:
            result = await integration.execute_tool(
                "telegram_webhook_update",
                {
                    "update": {
                        "update_id": 120,
                        "callback_query": {
                            "id": "cb-unknown",
                            "data": "noop:something",
                            "message": {"message_id": 9, "chat": {"id": 5}},
                        },
                    }
                },
            )
            assert result["ok"] is True
            assert result["result"]["callback"]["handled"] is False
            assert result["result"]["callback"]["action"] == "none"
            mock_answer.assert_awaited_once_with("cb-unknown", text="Received")
            assert integration.config.polling_offset == 121
        await integration.disconnect()

    asyncio.run(run())


def test_telegram_send_message_supports_reply_markup() -> None:
    """telegram_send_message should forward inline keyboard reply_markup payloads."""

    async def run() -> None:
        integration = TelegramIntegration(TelegramConfig(bot_token="123:ABC"))
        integration.connected = True
        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"ok": True, "result": {"message_id": 1}}
            result = await integration.execute_tool(
                "telegram_send_message",
                {
                    "chat_id": 1,
                    "text": "choose\\nmode",
                    "parse_mode": "MarkdownV2",
                    "reply_markup": {
                        "inline_keyboard": [[{"text": "Code", "callback_data": "mode:code"}]],
                    },
                },
            )
            assert result["ok"] is True
            mock_request.assert_awaited_once_with(
                "sendMessage",
                json={
                    "chat_id": 1,
                    "text": "choose\nmode",
                    "parse_mode": "MarkdownV2",
                    "reply_markup": {
                        "inline_keyboard": [[{"text": "Code", "callback_data": "mode:code"}]],
                    },
                },
            )
        await integration.disconnect()

    asyncio.run(run())


def test_mode_transition_webhook_and_polling_paths() -> None:
    """Connect should preserve webhook/polling parity and clear stale mode state."""

    async def run() -> None:
        integration = TelegramIntegration()
        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [
                {"ok": True, "result": {"username": "aegisbot"}},
                {"ok": True, "result": True},
                {"ok": True, "result": {"username": "aegisbot"}},
                {"ok": True, "result": True},
            ]
            webhook_connection = await integration.connect(
                {
                    "bot_token": "123:ABC",
                    "delivery_mode": "webhook",
                    "webhook_url": "https://example.com/hook",
                    "webhook_secret": "s",
                }
            )
            assert webhook_connection["connected"] is True
            assert integration.config.polling_offset == 0

            polling_connection = await integration.connect(
                {
                    "bot_token": "123:ABC",
                    "delivery_mode": "polling",
                }
            )
            assert polling_connection["connected"] is True
            assert integration.config.polling_offset == 0

            called_methods = [call.args[0] for call in mock_request.await_args_list]
            assert called_methods == ["getMe", "setWebhook", "getMe", "deleteWebhook"]
        await integration.disconnect()

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
