"""Tests for /mode slash command behavior."""

from __future__ import annotations

import asyncio
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock, patch


def test_mode_command_updates_runtime_mode() -> None:
    """/mode should set and report active runtime mode."""
    main_mod = import_module("main")
    runtime = main_mod.SessionRuntime()
    user_id = "mode-test-user"
    main_mod._user_runtimes[user_id] = runtime

    try:
        reply = asyncio.run(
            main_mod._handle_slash_command(
                text="/mode code",
                owner_uid=user_id,
                platform="telegram",
                integration_id="tg-1",
                chat_id=123,
            )
        )
        assert reply
        assert "Code" in reply
        assert runtime.settings.get("agent_mode") == "code"

        status_reply = asyncio.run(
            main_mod._handle_slash_command(
                text="/mode",
                owner_uid=user_id,
                platform="web",
                integration_id="tg-1",
                chat_id=123,
            )
        )
        assert isinstance(status_reply, str)
        assert "Code" in status_reply
    finally:
        main_mod._user_runtimes.pop(user_id, None)


def test_mode_command_renders_inline_keyboard_for_telegram() -> None:
    """/mode without args should return Telegram inline keyboard payload."""
    main_mod = import_module("main")
    runtime = main_mod.SessionRuntime()
    user_id = "mode-inline-user"
    main_mod._user_runtimes[user_id] = runtime

    try:
        reply = asyncio.run(
            main_mod._handle_slash_command(
                text="/mode",
                owner_uid=user_id,
                platform="telegram",
                integration_id="tg-1",
                chat_id=123,
            )
        )
        assert isinstance(reply, dict)
        assert "Current mode" in str(reply.get("text", ""))
        inline_keyboard = reply.get("reply_markup", {}).get("inline_keyboard", [])
        assert len(inline_keyboard) == len(main_mod.MODE_LABELS)
        callback_values = {row[0]["callback_data"] for row in inline_keyboard if row and isinstance(row[0], dict)}
        assert callback_values == {f"mode:{mode_name}" for mode_name in main_mod.MODE_LABELS}
    finally:
        main_mod._user_runtimes.pop(user_id, None)


def test_mode_callback_selection_updates_runtime_mode() -> None:
    """Telegram callback mode selection should update runtime mode and send confirmation."""
    main_mod = import_module("main")
    runtime = main_mod.SessionRuntime()
    user_id = "mode-callback-user"
    integration_id = "tg-mode-callback"
    main_mod._user_runtimes[user_id] = runtime

    try:
        from fastapi.testclient import TestClient

        update_payload = {
            "update_id": 42,
            "callback_query": {
                "id": "cb-1",
                "data": "mode:planner",
                "message": {"chat": {"id": 777}, "message_id": 9},
            },
        }
        main_mod.telegram_registry._integrations[integration_id] = object()
        main_mod.telegram_registry._configs[integration_id] = {"owner_user_id": user_id, "webhook_secret": ""}
        with patch.object(main_mod.telegram_registry, "get_telegram") as mock_get_integration:
            integration = MagicMock()
            integration.validate_webhook_secret.return_value = True
            integration.execute_tool = AsyncMock(return_value={"ok": True})
            mock_get_integration.return_value = integration
            with TestClient(main_mod.app) as test_client:
                response = test_client.post(
                    f"/api/integrations/telegram/webhook/{integration_id}",
                    json=update_payload,
                )

        assert response.status_code == 200
        assert runtime.settings.get("agent_mode") == "planner"
        integration.execute_tool.assert_any_await("telegram_webhook_update", {"update": update_payload})
        integration.execute_tool.assert_any_await(
            "telegram_send_message",
            {"chat_id": 777, "text": "✅ Mode switched to *Planner*"},
        )
    finally:
        main_mod._user_runtimes.pop(user_id, None)
        main_mod.telegram_registry._integrations.pop(integration_id, None)
        main_mod.telegram_registry._configs.pop(integration_id, None)


def test_mode_webhook_renders_inline_keyboard_message() -> None:
    """/mode webhook command should send current mode + inline keyboard."""
    main_mod = import_module("main")
    runtime = main_mod.SessionRuntime()
    user_id = "mode-webhook-user"
    integration_id = "tg-mode-inline"
    main_mod._user_runtimes[user_id] = runtime

    try:
        from fastapi.testclient import TestClient

        update_payload = {
            "update_id": 88,
            "message": {"message_id": 11, "chat": {"id": 999}, "from": {"id": 555}, "text": "/mode"},
        }
        main_mod.telegram_registry._integrations[integration_id] = object()
        main_mod.telegram_registry._configs[integration_id] = {"owner_user_id": user_id, "webhook_secret": ""}
        with patch.object(main_mod.telegram_registry, "get_telegram") as mock_get_integration:
            integration = MagicMock()
            integration.validate_webhook_secret.return_value = True
            integration.execute_tool = AsyncMock(return_value={"ok": True})
            mock_get_integration.return_value = integration
            with TestClient(main_mod.app) as test_client:
                response = test_client.post(
                    f"/api/integrations/telegram/webhook/{integration_id}",
                    json=update_payload,
                )

        assert response.status_code == 200
        integration.execute_tool.assert_any_await("telegram_webhook_update", {"update": update_payload})
        send_call = next(
            call
            for call in integration.execute_tool.await_args_list
            if call.args and call.args[0] == "telegram_send_message"
        )
        payload = send_call.args[1]
        assert payload["chat_id"] == "999"
        assert "Current mode" in payload["text"]
        inline_keyboard = payload["reply_markup"]["inline_keyboard"]
        assert len(inline_keyboard) == len(main_mod.MODE_LABELS)
    finally:
        main_mod._user_runtimes.pop(user_id, None)
        main_mod.telegram_registry._integrations.pop(integration_id, None)
        main_mod.telegram_registry._configs.pop(integration_id, None)
