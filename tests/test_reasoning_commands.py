"""Regression tests for canonical reasoning controls across channel runtimes."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from importlib import import_module
from typing import Any

from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.reasoning import (
    apply_reasoning_level,
    apply_reasoning_level_for_model,
    clamp_reasoning_level_for_model,
    normalize_reasoning_level,
    runtime_reasoning_level,
    supported_reasoning_levels,
)
from integrations.discord import DiscordIntegration
from integrations.slack_connector import SlackIntegration
from integrations.telegram import TelegramIntegration


class _StubTelegramIntegration(TelegramIntegration):
    def __init__(self) -> None:
        super().__init__()
        self.edits: list[dict[str, Any]] = []

    def validate_webhook_secret(self, secret: str) -> bool:
        return secret == "secret-1"

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "telegram_edit_message":
            self.edits.append(params)
        return {"ok": True, "tool": tool_name, "result": params}


class _StubChannelAdapter:
    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.sent: list[tuple[str, str, dict[str, Any] | None]] = []

    async def handle_event(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        _ = payload, headers
        return {"ok": True, "envelope": {}}

    def extract_mode_selection(self, payload: dict[str, Any]) -> str | None:
        _ = payload
        return None

    def extract_reasoning_selection(self, payload: dict[str, Any]) -> str | None:
        if self.platform == "telegram":
            callback = payload.get("callback_query") if isinstance(payload, dict) else {}
            return TelegramIntegration.extract_reasoning_selection((callback or {}).get("data"))
        if self.platform == "slack":
            return SlackIntegration.extract_reasoning_selection(payload)
        if self.platform == "discord":
            return DiscordIntegration.extract_reasoning_selection(payload)
        return None

    def extract_message(self, payload: dict[str, Any]) -> Any:
        class _Inbound:
            destination: str | None = None
            text: str | None = None
            message_id: str | None = None

        return _Inbound()

    async def send_text(self, destination: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        self.sent.append((destination, text, metadata))
        return {"ok": True, "channel": destination, "text": text}

    async def test_connection(self) -> dict[str, Any]:
        return {"ok": True}


def test_reasoning_normalization_and_aliases() -> None:
    assert normalize_reasoning_level("none") == "none"
    assert normalize_reasoning_level("XHIGH") == "xhigh"
    assert normalize_reasoning_level("on") == "medium"
    assert normalize_reasoning_level("off") == "none"
    assert normalize_reasoning_level("1") == "medium"
    assert normalize_reasoning_level("0") == "none"

    settings: dict[str, Any] = {}
    apply_reasoning_level(settings, "none")
    assert settings["reasoning_enabled"] is False
    assert settings["reasoning_effort"] == "none"

    apply_reasoning_level(settings, "minimal")
    assert settings["reasoning_enabled"] is True
    assert settings["reasoning_effort"] == "minimal"


def test_provider_model_reasoning_effort_clamp() -> None:
    assert supported_reasoning_levels("fireworks", "accounts/fireworks/models/kimi-k2p5") == ("none",)
    assert clamp_reasoning_level_for_model("fireworks", "accounts/fireworks/models/kimi-k2p5", "medium") == "none"

    assert supported_reasoning_levels("google", "gemini-2.5-pro") == ("none", "low", "medium", "high")
    assert clamp_reasoning_level_for_model("google", "gemini-2.5-pro", "xhigh") == "high"
    assert clamp_reasoning_level_for_model("xai", "grok-3-mini", "minimal") == "low"
    assert clamp_reasoning_level_for_model("openai", "gpt-5", "minimal") == "minimal"
    assert clamp_reasoning_level_for_model("chronos", "nvidia/nemotron-3-super-120b-a12b:free", "high") == "none"
    assert clamp_reasoning_level_for_model("openrouter", "qwen/qwen3-max-thinking", "xhigh") == "high"
    assert clamp_reasoning_level_for_model("anthropic", "claude-opus-4-6", "high") == "high"
    assert clamp_reasoning_level_for_model("openrouter", "anthropic/claude-opus-4.6", "high") == "none"

    settings = {"enable_reasoning": True, "reasoning_effort": "xhigh"}
    applied = apply_reasoning_level_for_model(
        settings,
        provider="fireworks",
        model="accounts/fireworks/models/kimi-k2p5",
        level=settings["reasoning_effort"],
    )
    assert applied == "none"
    assert settings["enable_reasoning"] is False
    assert settings["reasoning_enabled"] is False
    assert settings["reasoning_effort"] == "none"


def test_web_runtime_settings_clamp_provider_model_effort() -> None:
    main_mod = import_module("main")

    fireworks = main_mod._merge_runtime_settings(
        {},
        {
            "provider": "fireworks",
            "model": "accounts/fireworks/models/kimi-k2p5",
            "enable_reasoning": True,
            "reasoning_enabled": True,
            "reasoning_effort": "medium",
        },
    )
    assert fireworks["reasoning_effort"] == "none"
    assert fireworks["enable_reasoning"] is False
    assert fireworks["reasoning_enabled"] is False

    gemini = main_mod._merge_runtime_settings(
        {},
        {
            "provider": "google",
            "model": "gemini-2.5-pro",
            "enable_reasoning": True,
            "reasoning_enabled": True,
            "reasoning_effort": "xhigh",
        },
    )
    assert gemini["reasoning_effort"] == "high"
    assert gemini["enable_reasoning"] is True
    assert gemini["reasoning_enabled"] is True


def test_reasoning_slash_command_and_legacy_reason_alias() -> None:
    main_mod = import_module("main")
    runtime = main_mod.SessionRuntime()
    user_id = "reason-user"
    main_mod._user_runtimes[user_id] = runtime
    try:
        response = asyncio.run(
            main_mod._handle_slash_command(
                text="/reasoning xhigh",
                owner_uid=user_id,
                platform="telegram",
                integration_id="tg-1",
                chat_id="101",
            )
        )
        assert response
        assert "Extra High" in str(response)
        assert runtime_reasoning_level(runtime.settings) == "xhigh"

        legacy = asyncio.run(
            main_mod._handle_slash_command(
                text="/reason off",
                owner_uid=user_id,
                platform="telegram",
                integration_id="tg-1",
                chat_id="101",
            )
        )
        assert legacy
        assert "None" in str(legacy)
        assert runtime_reasoning_level(runtime.settings) == "none"
    finally:
        main_mod._user_runtimes.pop(user_id, None)


def test_telegram_reasoning_inline_callback_updates_runtime() -> None:
    main_mod = import_module("main")
    owner_uid = "tg-owner"
    runtime = main_mod.SessionRuntime()
    main_mod._user_runtimes[owner_uid] = runtime

    stub_integration = _StubTelegramIntegration()
    adapter = _StubChannelAdapter("telegram")
    adapter.integration = stub_integration
    main_mod.channel_registry.upsert(
        "telegram",
        "tg-test",
        adapter,
        {"owner_user_id": owner_uid, "webhook_secret": "secret-1"},
    )

    try:
        client = TestClient(main_mod.app)
        response = client.post(
            "/api/integrations/telegram/webhook/tg-test",
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret-1"},
            json={
                "callback_query": {
                    "id": "cb-1",
                    "data": "reasoning:high",
                    "message": {"chat": {"id": 111}, "message_id": 222},
                }
            },
        )
        assert response.status_code == 200
        assert runtime_reasoning_level(runtime.settings) == "high"
        assert stub_integration.edits
        assert "Reasoning set to *High*" in stub_integration.edits[-1]["text"]
    finally:
        main_mod._user_runtimes.pop(owner_uid, None)


def test_slack_reasoning_slash_and_interactive_flow() -> None:
    main_mod = import_module("main")
    owner_uid = "slack-owner"
    runtime = main_mod.SessionRuntime()
    main_mod._user_runtimes[owner_uid] = runtime

    adapter = _StubChannelAdapter("slack")
    integration = SlackIntegration()
    integration._signing_secret = "slack-secret"
    adapter.integration = integration
    main_mod.channel_registry.upsert("slack", "sl-1", adapter, {"owner_user_id": owner_uid, "signing_secret": "slack-secret"})
    original_log = main_mod._log_platform_message
    async def _noop_log(*args: Any, **kwargs: Any) -> None:
        _ = args, kwargs
    main_mod._log_platform_message = _noop_log

    try:
        client = TestClient(main_mod.app)
        ts = str(int(time.time()))
        body_one = json.dumps({"type": "command", "command": "/reasoning", "text": "", "channel_id": "C1"}).encode("utf-8")
        sig_one = "v0=" + hmac.new(
            b"slack-secret",
            f"v0:{ts}:{body_one.decode('utf-8')}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        bare = client.post(
            "/api/integrations/slack/webhook/sl-1",
            content=body_one,
            headers={
                "content-type": "application/json",
                "x-slack-request-timestamp": ts,
                "x-slack-signature": sig_one,
            },
        )
        assert bare.status_code == 200
        assert adapter.sent
        assert adapter.sent[-1][0] == "C1"
        assert adapter.sent[-1][2] and "blocks" in (adapter.sent[-1][2] or {})

        body_two = json.dumps(
            {
                "type": "block_actions",
                "channel": {"id": "C1"},
                "actions": [
                    {
                        "action_id": "reasoning_select",
                        "selected_option": {
                            "value": "reasoning:xhigh",
                            "text": {"type": "plain_text", "text": "Extra High"},
                        },
                    }
                ],
            }
        ).encode("utf-8")
        sig_two = "v0=" + hmac.new(
            b"slack-secret",
            f"v0:{ts}:{body_two.decode('utf-8')}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        updated = client.post(
            "/api/integrations/slack/webhook/sl-1",
            content=body_two,
            headers={
                "content-type": "application/json",
                "x-slack-request-timestamp": ts,
                "x-slack-signature": sig_two,
            },
        )
        assert updated.status_code == 200
        assert runtime_reasoning_level(runtime.settings) == "xhigh"
        assert adapter.sent[-1][1] == "Reasoning set to Extra High"
    finally:
        main_mod._log_platform_message = original_log
        main_mod._user_runtimes.pop(owner_uid, None)


def test_discord_reasoning_command_and_component_flow() -> None:
    main_mod = import_module("main")
    owner_uid = "discord-owner"
    runtime = main_mod.SessionRuntime()
    main_mod._user_runtimes[owner_uid] = runtime

    adapter = _StubChannelAdapter("discord")
    private_key = Ed25519PrivateKey.generate()
    public_key_hex = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    integration = DiscordIntegration()
    integration._public_key_hex = public_key_hex
    adapter.integration = integration
    main_mod.channel_registry.upsert("discord", "dc-1", adapter, {"owner_user_id": owner_uid, "public_key": public_key_hex})
    original_log = main_mod._log_platform_message
    async def _noop_log(*args: Any, **kwargs: Any) -> None:
        _ = args, kwargs
    main_mod._log_platform_message = _noop_log

    try:
        client = TestClient(main_mod.app)
        timestamp = str(int(time.time()))
        body_one = json.dumps(
            {
                "type": 2,
                "channel_id": "D1",
                "data": {"name": "reasoning", "options": [{"name": "effort", "value": "minimal"}]},
            }
        ).encode("utf-8")
        sig_one = private_key.sign(timestamp.encode("utf-8") + body_one).hex()
        set_minimal = client.post(
            "/api/integrations/discord/webhook/dc-1",
            content=body_one,
            headers={
                "content-type": "application/json",
                "x-signature-timestamp": timestamp,
                "x-signature-ed25519": sig_one,
            },
        )
        assert set_minimal.status_code == 200
        assert runtime_reasoning_level(runtime.settings) == "minimal"

        body_two = json.dumps(
            {
                "type": 3,
                "channel_id": "D1",
                "data": {"custom_id": "reasoning_select", "values": ["reasoning:none"]},
            }
        ).encode("utf-8")
        sig_two = private_key.sign(timestamp.encode("utf-8") + body_two).hex()
        set_none = client.post(
            "/api/integrations/discord/webhook/dc-1",
            content=body_two,
            headers={
                "content-type": "application/json",
                "x-signature-timestamp": timestamp,
                "x-signature-ed25519": sig_two,
            },
        )
        assert set_none.status_code == 200
        assert runtime_reasoning_level(runtime.settings) == "none"
        assert adapter.sent[-1][1] == "Reasoning set to None"
    finally:
        main_mod._log_platform_message = original_log
        main_mod._user_runtimes.pop(owner_uid, None)
