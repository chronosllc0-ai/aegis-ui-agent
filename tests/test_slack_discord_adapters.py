"""Slack/Discord adapter modernization coverage."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

from backend.integrations.contracts import ChannelAdapter
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
