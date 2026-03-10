"""Tests for Slack/Discord/Brave client behavior including rate limits."""

from __future__ import annotations

import asyncio

import pytest

from integrations.brave_search import BraveSearchIntegration
from integrations.discord import DiscordIntegration
from integrations.manager import IntegrationManager
from integrations.slack_connector import SlackIntegration


class _MockResponse:
    def __init__(self, status_code: int = 200, body: dict | None = None, headers: dict[str, str] | None = None, text: str = "json") -> None:
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


def test_slack_429_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        integration = SlackIntegration()
        responses = [
            _MockResponse(status_code=429, body={"ok": False}, headers={"Retry-After": "0"}),
            _MockResponse(status_code=200, body={"ok": True, "team": "aegis", "user": "bot"}),
        ]

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                return responses.pop(0)

        monkeypatch.setattr("integrations.slack_connector.httpx.AsyncClient", lambda *args, **kwargs: _Client())
        result = await integration.execute_tool(
            IntegrationManager()._record_for("u1", "slack"),
            {"bot_token": "x"},
            "slack.auth_test",
            {},
        )
        assert result.ok is True

    asyncio.run(scenario())


def test_discord_429_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        integration = DiscordIntegration()
        responses = [
            _MockResponse(status_code=429, body={"retry_after": 0, "global": True}, headers={"X-RateLimit-Bucket": "b1"}),
            _MockResponse(status_code=200, body={"id": "1", "username": "bot"}),
        ]

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def request(self, *args, **kwargs):
                return responses.pop(0)

        monkeypatch.setattr("integrations.discord.httpx.AsyncClient", lambda *args, **kwargs: _Client())
        result = await integration.execute_tool(
            IntegrationManager()._record_for("u2", "discord"),
            {"bot_token": "x"},
            "discord.get_me",
            {},
        )
        assert result.ok is True
        assert integration.last_rate_limit_incident is not None

    asyncio.run(scenario())


def test_brave_search(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        integration = BraveSearchIntegration()

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, *args, **kwargs):
                return _MockResponse(status_code=200, body={"web": {"results": [{"title": "Aegis"}]}})

        monkeypatch.setattr("integrations.brave_search.httpx.AsyncClient", lambda *args, **kwargs: _Client())
        result = await integration.execute_tool(
            IntegrationManager()._record_for("u3", "brave-search"),
            {"api_key": "x"},
            "brave.web_search",
            {"q": "aegis"},
        )
        assert result.ok is True
        assert result.data["results"][0]["title"] == "Aegis"

    asyncio.run(scenario())
