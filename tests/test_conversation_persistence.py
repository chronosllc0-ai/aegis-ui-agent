"""Regression tests for phase-3 conversation persistence."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import auth
import main
from backend import database
from backend.conversation_service import append_message, get_or_create_conversation, update_conversation_title
from backend.database import Conversation, ConversationMessage, User
from config import settings


def _init_test_db(tmp_path: Path, name: str) -> None:
    """Initialize an isolated SQLite database for one persistence test."""
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / name}")
    asyncio.run(database.create_tables())


async def _seed_user(uid: str, email: str, name: str = "Test User") -> None:
    """Insert a simple active user record for FK-safe conversation logging."""
    async with database._session_factory() as session:  # type: ignore[union-attr]
        session.add(
            User(
                uid=uid,
                provider="password",
                provider_id=email,
                email=email,
                name=name,
                role="user",
                status="active",
            )
        )
        await session.commit()


async def _fetch_conversations() -> list[Conversation]:
    """Return all conversations ordered by creation time."""
    async with database._session_factory() as session:  # type: ignore[union-attr]
        return (
            await session.execute(
                select(Conversation).order_by(Conversation.created_at.asc(), Conversation.id.asc())
            )
        ).scalars().all()


async def _fetch_messages(conversation_id: str) -> list[ConversationMessage]:
    """Return all messages for one conversation ordered by creation time."""
    async with database._session_factory() as session:  # type: ignore[union-attr]
        return (
            await session.execute(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation_id)
                .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
            )
        ).scalars().all()


def test_conversation_service_reuses_active_conversation_and_persists_metadata(tmp_path: Path) -> None:
    """The service should deduplicate active conversations and store message metadata."""
    _init_test_db(tmp_path, "conversation_service.db")
    asyncio.run(_seed_user("password:user@example.com", "user@example.com"))

    async def _run() -> None:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            first = await get_or_create_conversation(
                session,
                "password:user@example.com",
                "web",
                "session-1",
                title="First title",
            )
            second = await get_or_create_conversation(
                session,
                "password:user@example.com",
                "web",
                "session-1",
                title="Ignored replacement",
            )
            assert first.id == second.id

            message = await append_message(
                session,
                first.id,
                "user",
                " hello world ",
                metadata={"source": "test", "action": "navigate"},
            )
            assert message is not None
            await update_conversation_title(session, first.id, "Renamed conversation")

        conversations = await _fetch_conversations()
        messages = await _fetch_messages(first.id)
        assert len(conversations) == 1
        assert conversations[0].title == "Renamed conversation"
        assert conversations[0].updated_at is not None
        assert len(messages) == 1
        assert messages[0].content == "hello world"
        assert messages[0].metadata_json == '{"source": "test", "action": "navigate"}'

    asyncio.run(_run())


class _StubExecutor:
    async def ensure_browser(self) -> None:
        return None

    async def screenshot(self) -> bytes:
        return b"fake_png"


class _StubOrchestrator:
    def __init__(self) -> None:
        self.executor = _StubExecutor()

    async def execute_task(
        self,
        session_id: str,
        instruction: str,
        on_step=None,
        on_frame=None,
        on_workflow_step=None,
        **kwargs,
    ) -> dict[str, Any]:
        if on_step:
            await on_step({"type": "message", "content": f"stub:{instruction}"})
        if on_frame:
            await on_frame("ZmFrZV9mcmFtZQ==")
        if on_workflow_step:
            await on_workflow_step(
                {
                    "step_id": "step-1",
                    "parent_step_id": None,
                    "action": "navigate",
                    "description": "stub step",
                    "status": "completed",
                    "timestamp": "2026-03-20T12:00:00Z",
                    "duration_ms": 5,
                    "screenshot": None,
                }
            )
        return {"status": "completed", "session_id": session_id, "instruction": instruction}


class _StubMessagingIntegration:
    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        return {"connected": True, "config": config}

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "tool": tool_name, "result": params}


def _configure_main_for_test(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """Make main.TestClient safe to use with the isolated test DB."""
    original_secret = settings.SESSION_SECRET
    settings.SESSION_SECRET = "test-session-secret"
    monkeypatch.setattr(main, "init_db", lambda url=None: None)

    async def _fake_create_tables() -> None:
        return None

    monkeypatch.setattr(main, "create_tables", _fake_create_tables)
    main.db_ready = True
    main.db_init_error = None
    main.db_init_task = None
    main.orchestrator = _StubOrchestrator()
    main.telegram_registry._integrations.clear()
    main.telegram_registry._configs.clear()
    main.slack_registry._integrations.clear()
    main.slack_registry._configs.clear()
    main.discord_registry._integrations.clear()
    main.discord_registry._configs.clear()
    return original_secret, auth._sign_session({"uid": "password:user@example.com", "email": "user@example.com"})


def test_websocket_navigation_persists_user_and_assistant_messages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Web navigation should create one web conversation with user and assistant messages."""
    _init_test_db(tmp_path, "websocket_conversations.db")
    asyncio.run(_seed_user("password:user@example.com", "user@example.com"))
    original_secret, token = _configure_main_for_test(monkeypatch)

    try:
        client = TestClient(main.app)
        client.cookies.set("aegis_session", token)
        with client.websocket_connect("/ws/navigate") as ws:
            assert ws.receive_json()["type"] == "frame"
            ws.send_json({"action": "navigate", "instruction": "open github"})
            assert ws.receive_json()["type"] == "step"
            assert ws.receive_json()["type"] == "frame"
            assert ws.receive_json()["type"] == "workflow_step"
            assert ws.receive_json()["type"] == "result"
            ws.send_json({"action": "stop"})

        conversations = asyncio.run(_fetch_conversations())
        assert len(conversations) == 1
        assert conversations[0].platform == "web"
        assert conversations[0].user_id == "password:user@example.com"
        assert conversations[0].title == "open github"

        messages = asyncio.run(_fetch_messages(conversations[0].id))
        assert [message.role for message in messages] == ["user", "assistant"]
        assert messages[0].content == "open github"
        assert messages[1].content == "Task completed: open github"
    finally:
        settings.SESSION_SECRET = original_secret
        main.orchestrator = None


@pytest.mark.parametrize(
    ("platform", "register_path", "send_path", "config_payload", "message_payload"),
    [
        (
            "slack",
            "/api/integrations/slack/register/integration-1",
            "/api/integrations/slack/integration-1/send_message",
            {"bot_token": "xoxb-test", "workspace": "Acme"},
            {"channel": "C123", "text": "hello slack"},
        ),
        (
            "discord",
            "/api/integrations/discord/register/integration-1",
            "/api/integrations/discord/integration-1/send_message",
            {"bot_token": "discord-test", "guild_id": "guild-1"},
            {"channel": "general", "text": "hello discord"},
        ),
    ],
)
def test_integration_registration_captures_owner_and_send_message_persists_conversation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    register_path: str,
    send_path: str,
    config_payload: dict[str, Any],
    message_payload: dict[str, Any],
) -> None:
    """Slack and Discord integrations should log outbound assistant messages for the owner."""
    _init_test_db(tmp_path, f"{platform}_conversations.db")
    asyncio.run(_seed_user("password:user@example.com", "user@example.com"))
    original_secret, token = _configure_main_for_test(monkeypatch)

    if platform == "slack":
        monkeypatch.setattr(main, "SlackIntegration", _StubMessagingIntegration)
    else:
        monkeypatch.setattr(main, "DiscordIntegration", _StubMessagingIntegration)

    try:
        client = TestClient(main.app)
        client.cookies.set("aegis_session", token)
        register_response = client.post(register_path, json=config_payload)
        assert register_response.status_code == 200

        if platform == "slack":
            assert main.slack_registry.get_config("integration-1")["owner_user_id"] == "password:user@example.com"
        else:
            assert main.discord_registry.get_config("integration-1")["owner_user_id"] == "password:user@example.com"

        send_response = client.post(send_path, json=message_payload)
        assert send_response.status_code == 200
        assert send_response.json()["ok"] is True

        conversations = asyncio.run(_fetch_conversations())
        assert len(conversations) == 1
        assert conversations[0].platform == platform
        assert conversations[0].user_id == "password:user@example.com"

        messages = asyncio.run(_fetch_messages(conversations[0].id))
        assert len(messages) == 1
        assert messages[0].role == "assistant"
        assert messages[0].content == message_payload["text"]
    finally:
        settings.SESSION_SECRET = original_secret
        main.orchestrator = None


def test_telegram_webhook_persists_inbound_user_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telegram webhooks should log inbound messages against the integration owner."""
    _init_test_db(tmp_path, "telegram_conversations.db")
    asyncio.run(_seed_user("password:user@example.com", "user@example.com"))
    original_secret, _ = _configure_main_for_test(monkeypatch)

    telegram_integration = _StubMessagingIntegration()
    main.telegram_registry.upsert(
        "telegram-1",
        telegram_integration,
        {"webhook_secret": "secret-123", "owner_user_id": "password:user@example.com"},
    )

    try:
        client = TestClient(main.app)
        response = client.post(
            "/api/integrations/telegram/webhook/telegram-1",
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret-123"},
            json={
                "message": {
                    "message_id": 77,
                    "chat": {"id": 555},
                    "text": "summarize the latest updates",
                }
            },
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True

        conversations = asyncio.run(_fetch_conversations())
        assert len(conversations) == 1
        assert conversations[0].platform == "telegram"
        assert conversations[0].platform_chat_id == "555"

        messages = asyncio.run(_fetch_messages(conversations[0].id))
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == "summarize the latest updates"
        assert messages[0].platform_message_id == "77"
    finally:
        settings.SESSION_SECRET = original_secret
        main.orchestrator = None
