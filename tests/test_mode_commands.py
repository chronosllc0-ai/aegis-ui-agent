"""Tests for /mode slash command behavior."""

from __future__ import annotations

import asyncio
from importlib import import_module


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
                platform="telegram",
                integration_id="tg-1",
                chat_id=123,
            )
        )
        assert status_reply
        assert "Code" in status_reply
    finally:
        main_mod._user_runtimes.pop(user_id, None)
