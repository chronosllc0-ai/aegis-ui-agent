"""Slack/Discord adapter modernization coverage."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

from backend.integrations.contracts import ChannelAdapter
from backend.integrations.capability_matrix import resolve_capability_status, unsupported_action_fallback
from config import settings
from integrations.discord import DiscordIntegration
from integrations.idempotency import DeliveryDeduper
from integrations.slack_connector import SlackIntegration


class _MockResponse:
    def __init__(self, *, status_code: int, payload: Any, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = str(payload)

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_slack_connect_supports_oauth_token() -> None:
    async def _run() -> None:
        integration = SlackIntegration()
        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"ok": True, "team": "Aegis"}
            result = await integration.connect({"oauth_token": "xoxb-123"})

        assert result["connected"] is True
        assert result["workspace"] == "Aegis"

    asyncio.run(_run())


def test_slack_handle_event_verification_and_idempotency() -> None:
    async def _run() -> None:
        integration = SlackIntegration()

        verification = await integration.handle_event({"type": "url_verification", "challenge": "abc"}, {})
        assert verification["response"] == {"challenge": "abc"}

        payload = {"type": "event_callback", "event_id": "evt-1", "event": {"type": "message", "channel": "C1"}}
        first = await integration.handle_event(payload, {})
        second = await integration.handle_event(payload, {})

        assert first["duplicate"] is False
        assert second["duplicate"] is True

    asyncio.run(_run())


def test_slack_send_edit_file_and_rate_limit_backoff() -> None:
    async def _run() -> None:
        integration = SlackIntegration()
        integration.connected = True
        integration._token = "xoxb-test"

        responses = [
            _MockResponse(status_code=429, payload={"ok": False, "error": "ratelimited"}, headers={"Retry-After": "0"}),
            _MockResponse(status_code=200, payload={"ok": True, "ts": "1.2", "channel": "C1"}),
        ]

        async def _request_side_effect(*args: Any, **kwargs: Any) -> _MockResponse:
            return responses.pop(0)

        with patch("integrations.slack_connector.httpx.AsyncClient.request", side_effect=_request_side_effect):
            sent = await integration.send_text("C1", "hello")

        assert sent["ok"] is True

        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"ok": True, "ts": "1.2"}
            edited = await integration.edit_text("C1", "1.2", "updated <danger>")
            sent_payload = mock_request.await_args.kwargs["json_payload"]
            assert sent_payload["text"] == "updated &lt;danger&gt;"
        assert edited["ok"] is True

        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request, patch(
            "integrations.slack_connector.httpx.AsyncClient.post", new_callable=AsyncMock
        ) as mock_post:
            mock_request.side_effect = [
                {"ok": True, "upload_url": "https://upload.test", "file_id": "F123"},
                {"ok": True, "file": {"id": "F123"}},
            ]
            mock_post.return_value = _MockResponse(status_code=200, payload={})
            upload = await integration.send_file("C1", b"abc", filename="a.txt", mime_type="text/plain", caption="hi")

        assert upload["ok"] is True

        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"ok": True}
            deleted = await integration.execute_tool("slack_delete_message", {"channel": "C1", "message_id": "1.2"})
        assert deleted["ok"] is True

        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"ok": True}
            reacted = await integration.execute_tool(
                "slack_react",
                {"channel": "C1", "message_id": "1.2", "reaction": ":white_check_mark:"},
            )
        assert reacted["ok"] is True

        with patch.object(integration, "send_text", new_callable=AsyncMock) as mock_send_text:
            mock_send_text.return_value = {"ok": True, "tool": "slack_send_message"}
            interactive = await integration.execute_tool(
                "slack_send_interactive",
                {"channel": "C1", "text": "controls", "blocks": "not-a-list"},
            )
            metadata = mock_send_text.await_args.kwargs["metadata"]
            assert isinstance(metadata.get("blocks"), list)
        assert interactive["ok"] is True

    asyncio.run(_run())


def test_discord_connect_send_edit_file_interaction_event() -> None:
    async def _run() -> None:
        integration = DiscordIntegration()
        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"id": "bot-1"}
            connected = await integration.connect({"bot_token": "discord-token", "guild_id": "g1"})

        assert connected["connected"] is True

        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"id": "m1", "content": "hello"}
            sent = await integration.send_text("c1", "@everyone **hello**")
            sent_payload = mock_request.await_args.kwargs["json_payload"]
            assert sent_payload["content"] == "@\u200beveryone \\*\\*hello\\*\\*"
        assert sent["ok"] is True

        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"id": "m1", "content": "updated"}
            edited = await integration.edit_text("c1", "m1", "updated")
        assert edited["ok"] is True

        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"id": "m2"}
            upload = await integration.send_file("c1", b"img", filename="x.png", mime_type="image/png", caption="frame")
        assert upload["ok"] is True

        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {}
            deleted = await integration.execute_tool("discord_delete_message", {"channel": "c1", "message_id": "m2"})
        assert deleted["ok"] is True

        with patch.object(integration, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {}
            reacted = await integration.execute_tool("discord_react", {"channel": "c1", "message_id": "m2", "reaction": "👍"})
        assert reacted["ok"] is True

        with patch.object(integration, "send_text", new_callable=AsyncMock) as mock_send_text:
            mock_send_text.return_value = {"ok": True, "tool": "discord_send_message"}
            interactive = await integration.execute_tool(
                "discord_send_interactive",
                {"channel": "c1", "text": "controls", "components": "not-a-list"},
            )
            metadata = mock_send_text.await_args.kwargs["metadata"]
            assert isinstance(metadata.get("components"), list)
        assert interactive["ok"] is True

        ping = await integration.handle_event({"type": 1, "id": "evt-1"}, {})
        assert ping["response"] == {"type": 1}

        command_payload = {
            "id": "evt-2",
            "type": 2,
            "channel_id": "c1",
            "data": {"name": "summarize", "options": [{"name": "text", "value": "hello"}]},
            "member": {"user": {"id": "u1"}},
        }
        normalized = await integration.handle_event(command_payload, {})
        assert normalized["envelope"]["event_type"] == "summarize"
        assert normalized["response"] == {"type": 5}

        control_command = await integration.handle_event(
            {"id": "evt-3", "type": 2, "channel_id": "c1", "data": {"name": "aegis-runtime-stop"}},
            {},
        )
        assert control_command["envelope"]["control_action"] == "runtime_stop"

        component_action = await integration.handle_event(
            {"id": "evt-4", "type": 3, "channel_id": "c1", "data": {"custom_id": "control:status"}},
            {},
        )
        assert component_action["envelope"]["control_action"] == "status"

    asyncio.run(_run())


def test_discord_rate_limit_backoff_and_contract_conformance() -> None:
    async def _run() -> None:
        integration = DiscordIntegration()
        integration.connected = True
        integration._token = "discord"

        responses = [
            _MockResponse(status_code=429, payload={"message": "rate", "retry_after": 0}),
            _MockResponse(status_code=200, payload={"id": "m1", "content": "ok"}),
        ]

        async def _request_side_effect(*args: Any, **kwargs: Any) -> _MockResponse:
            return responses.pop(0)

        with patch("integrations.discord.httpx.AsyncClient.request", side_effect=_request_side_effect):
            result = await integration.send_text("c1", "hello")

        assert result["ok"] is True

        assert isinstance(integration, ChannelAdapter)
        assert isinstance(SlackIntegration(), ChannelAdapter)

    asyncio.run(_run())


def test_delivery_deduper_is_bounded() -> None:
    deduper = DeliveryDeduper(max_entries=3)

    assert deduper.seen_or_add("a") is False
    assert deduper.seen_or_add("b") is False
    assert deduper.seen_or_add("c") is False
    assert deduper.seen_or_add("d") is False

    # oldest id should be evicted once capacity is exceeded
    assert deduper.seen_or_add("a") is False
    assert deduper.seen_or_add("d") is True


def test_mode_selector_helpers_extract_expected_values() -> None:
    slack_blocks = SlackIntegration.mode_selector_blocks(
        current_mode_label="Planner",
        mode_labels={"planner": "Planner", "code": "Code"},
    )
    assert isinstance(slack_blocks, list)
    slack_selection = SlackIntegration.extract_mode_selection(
        {"actions": [{"action_id": "mode_select", "value": "mode:code"}]}
    )
    assert slack_selection == "code"

    discord_components = DiscordIntegration.mode_selector_components({"planner": "Planner", "code": "Code"})
    assert isinstance(discord_components, list)
    discord_selection = DiscordIntegration.extract_mode_selection({"data": {"custom_id": "mode:planner"}})
    assert discord_selection == "planner"


def test_capability_matrix_fallbacks_for_unknown_tools() -> None:
    async def _run() -> None:
        slack = SlackIntegration()
        slack.connected = True
        slack._token = "xoxb"
        slack_fallback = await slack.execute_tool("slack_topic_create", {"channel": "C1"})
        assert slack_fallback["fallback"] is True

        discord = DiscordIntegration()
        discord.connected = True
        discord._token = "bot"
        discord_fallback = await discord.execute_tool("discord_topic_create", {"channel": "c1"})
        assert discord_fallback["fallback"] is True

        slash_control = await slack.handle_event({"type": "command", "command": "/aegis-status", "channel_id": "C1"}, {})
        assert slash_control["envelope"]["control_action"] == "status"

    asyncio.run(_run())


def test_capability_matrix_unknown_platform_returns_graceful_fallback() -> None:
    status, capability = resolve_capability_status("custom-platform", "custom_tool")
    assert status == "unsupported"
    assert capability == ""

    payload = unsupported_action_fallback("custom-platform", "custom_tool")
    assert payload["fallback"] is True


def test_slack_advanced_tool_flag_blocks_interactive_controls(monkeypatch) -> None:
    """Staged rollout flag should disable Slack advanced interactive tool path."""
    async def _run() -> None:
        integration = SlackIntegration()
        integration.connected = True
        integration._token = "xoxb-test"

        monkeypatch.setattr(settings, "CHANNEL_TOOLS_SLACK_ADVANCED_ENABLED", False)
        blocked = await integration.execute_tool(
            "slack_send_interactive",
            {"channel": "C1", "text": "controls"},
        )
        assert blocked["ok"] is False
        assert blocked["fallback"] is True
        assert "feature flag" in str(blocked["error"]).lower()

    asyncio.run(_run())


def test_discord_advanced_tool_flag_blocks_interactive_controls(monkeypatch) -> None:
    """Staged rollout flag should disable Discord advanced interactive tool path."""
    async def _run() -> None:
        integration = DiscordIntegration()
        integration.connected = True
        integration._token = "discord-token"

        monkeypatch.setattr(settings, "CHANNEL_TOOLS_DISCORD_ADVANCED_ENABLED", False)
        blocked = await integration.execute_tool(
            "discord_send_interactive",
            {"channel": "c1", "text": "controls"},
        )
        assert blocked["ok"] is False
        assert blocked["fallback"] is True
        assert "feature flag" in str(blocked["error"]).lower()

    asyncio.run(_run())
