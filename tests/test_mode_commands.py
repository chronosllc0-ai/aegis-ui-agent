"""Tests for slash command behavior."""

from __future__ import annotations

import asyncio
from importlib import import_module


def test_model_command_reports_runtime_model() -> None:
    """/model should report active runtime model."""
    main_mod = import_module("main")
    runtime = main_mod.SessionRuntime()
    user_id = "mode-test-user"
    main_mod._user_runtimes[user_id] = runtime

    try:
        reply = asyncio.run(
            main_mod._handle_slash_command(
                text="/model",
                owner_uid=user_id,
                platform="telegram",
                integration_id="tg-1",
                chat_id=123,
            )
        )
        assert reply
        assert "Current model" in reply
    finally:
        main_mod._user_runtimes.pop(user_id, None)


def test_subagent_steer_command_alias_routes_to_runtime_message_path() -> None:
    """/subagent steer should forward to subagent_manager.send_message like message_subagent."""
    main_mod = import_module("main")
    runtime = main_mod.SessionRuntime()
    user_id = "subagent-steer-user"
    calls: list[tuple[str, str]] = []

    async def _fake_send_message(sub_id: str, message: str) -> bool:
        calls.append((sub_id, message))
        return True

    runtime.subagent_manager.send_message = _fake_send_message  # type: ignore[method-assign]
    main_mod._user_runtimes[user_id] = runtime

    try:
        reply = asyncio.run(
            main_mod._handle_slash_command(
                text="/subagent steer sub-42 focus on blockers first",
                owner_uid=user_id,
                platform="telegram",
                integration_id="tg-1",
                chat_id=123,
            )
        )
        assert reply
        assert "steering sent" in reply.lower()
        assert calls == [("sub-42", "focus on blockers first")]
    finally:
        main_mod._user_runtimes.pop(user_id, None)


def test_subagent_steering_payload_encodes_priority_annotation() -> None:
    """Subagent steering helper should preserve message text and prepend valid priorities."""
    main_mod = import_module("main")

    payload = main_mod._build_subagent_steering_payload("focus blockers first", priority="urgent")
    assert payload == "[priority:urgent] focus blockers first"

    payload_without_priority = main_mod._build_subagent_steering_payload("focus blockers first", priority="invalid")
    assert payload_without_priority == "focus blockers first"
