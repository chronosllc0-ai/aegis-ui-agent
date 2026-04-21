"""Regression tests for sessions-v2 migration rollout behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

import auth
import main
from backend import database
from backend.database import ChatSession, ChatSessionMessage, Conversation, ConversationMessage, LegacySessionArchive, User
from config import settings


def _init_test_db(tmp_path: Path, name: str) -> None:
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / name}")
    asyncio.run(database.create_tables())


async def _seed_user(uid: str, email: str) -> None:
    async with database._session_factory() as session:  # type: ignore[union-attr]
        session.add(User(uid=uid, provider="password", provider_id=email, email=email, name="User", role="user", status="active"))
        await session.commit()


def _configure_main_flags() -> tuple[dict[str, bool | str], str]:
    original = {
        "FEATURE_FLAG_SESSIONS_V2": settings.FEATURE_FLAG_SESSIONS_V2,
        "SESSIONS_V2_DUAL_WRITE": settings.SESSIONS_V2_DUAL_WRITE,
        "SESSIONS_V2_LEGACY_FALLBACK": settings.SESSIONS_V2_LEGACY_FALLBACK,
        "SESSION_SECRET": settings.SESSION_SECRET,
    }
    settings.FEATURE_FLAG_SESSIONS_V2 = True
    settings.SESSIONS_V2_DUAL_WRITE = True
    settings.SESSIONS_V2_LEGACY_FALLBACK = False
    settings.SESSION_SECRET = "test-secret"
    token = auth._sign_session({"uid": "password:user@example.com", "email": "user@example.com"})
    return original, token


def _restore_main_flags(original: dict[str, bool | str]) -> None:
    settings.FEATURE_FLAG_SESSIONS_V2 = bool(original["FEATURE_FLAG_SESSIONS_V2"])
    settings.SESSIONS_V2_DUAL_WRITE = bool(original["SESSIONS_V2_DUAL_WRITE"])
    settings.SESSIONS_V2_LEGACY_FALLBACK = bool(original["SESSIONS_V2_LEGACY_FALLBACK"])
    settings.SESSION_SECRET = str(original["SESSION_SECRET"])


def test_send_start_path_dual_writes_session_and_conversation(tmp_path: Path) -> None:
    _init_test_db(tmp_path, "send_start.db")
    asyncio.run(_seed_user("password:user@example.com", "user@example.com"))
    original, token = _configure_main_flags()
    try:
        client = TestClient(main.app)
        client.cookies.set("aegis_session", token)
        response = client.post(
            "/api/sessions/agent:main:web:workspace:conversation:alpha/send",
            json={"content": "Kick off migration"},
        )
        assert response.status_code == 200
        async def _assert_rows() -> None:
            async with database._session_factory() as session:  # type: ignore[union-attr]
                assert (await session.execute(select(ChatSession))).scalar_one_or_none() is not None
                assert (await session.execute(select(ChatSessionMessage))).scalar_one_or_none() is not None
                assert (await session.execute(select(Conversation))).scalar_one_or_none() is not None
                assert (await session.execute(select(ConversationMessage))).scalar_one_or_none() is not None
        asyncio.run(_assert_rows())
    finally:
        _restore_main_flags(original)


def test_session_switch_persistence_keeps_messages_isolated(tmp_path: Path) -> None:
    _init_test_db(tmp_path, "session_switch.db")
    asyncio.run(_seed_user("password:user@example.com", "user@example.com"))
    original, token = _configure_main_flags()
    try:
        client = TestClient(main.app)
        client.cookies.set("aegis_session", token)
        first_session = "agent:main:web:workspace:conversation:first"
        second_session = "agent:main:web:workspace:conversation:second"
        assert client.post(f"/api/sessions/{first_session}/send", json={"content": "First trail"}).status_code == 200
        assert client.post(f"/api/sessions/{second_session}/send", json={"content": "Second trail"}).status_code == 200
        first_messages = client.get(f"/api/sessions/{first_session}/messages").json()["messages"]
        second_messages = client.get(f"/api/sessions/{second_session}/messages").json()["messages"]
        assert [item["content"] for item in first_messages] == ["First trail"]
        assert [item["content"] for item in second_messages] == ["Second trail"]
    finally:
        _restore_main_flags(original)


def test_subagent_spawn_creates_session_v2_entry(tmp_path: Path) -> None:
    _init_test_db(tmp_path, "subagent_spawn.db")
    asyncio.run(_seed_user("password:user@example.com", "user@example.com"))
    original, token = _configure_main_flags()
    try:
        client = TestClient(main.app)
        client.cookies.set("aegis_session", token)
        response = client.post(
            "/api/sessions/spawn",
            json={"parent_session_id": "agent:main:web:workspace:conversation:parent", "instruction": "Research risks"},
        )
        assert response.status_code == 200
        session_id = response.json()["session"]["session_id"]
        async def _assert_session() -> None:
            async with database._session_factory() as session:  # type: ignore[union-attr]
                row = (
                    await session.execute(
                        select(ChatSession).where(ChatSession.platform == "web", ChatSession.session_id == session_id)
                    )
                ).scalar_one_or_none()
                assert row is not None
                assert row.parent_session_id == "agent:main:web:workspace:conversation:parent"
        asyncio.run(_assert_session())
    finally:
        _restore_main_flags(original)


def test_system_events_are_excluded_from_session_chat_messages(tmp_path: Path) -> None:
    _init_test_db(tmp_path, "system_events.db")
    asyncio.run(_seed_user("password:user@example.com", "user@example.com"))
    original, token = _configure_main_flags()
    try:
        client = TestClient(main.app)
        client.cookies.set("aegis_session", token)
        session_id = "agent:main:web:workspace:conversation:system-filter"
        assert client.post(f"/api/sessions/{session_id}/send", json={"content": "Visible message"}).status_code == 200

        async def _insert_system_event() -> None:
            async with database._session_factory() as session:  # type: ignore[union-attr]
                row = (
                    await session.execute(
                        select(ChatSession).where(ChatSession.platform == "web", ChatSession.session_id == session_id)
                    )
                ).scalar_one()
                session.add(ChatSessionMessage(session_ref_id=row.id, role="system", content="system-only", metadata_json=None))
                await session.commit()

        asyncio.run(_insert_system_event())
        messages = client.get(f"/api/sessions/{session_id}/messages").json()["messages"]
        assert [item["role"] for item in messages] == ["user"]
    finally:
        _restore_main_flags(original)


def test_list_sessions_archives_legacy_rows_and_bootstraps_main(tmp_path: Path) -> None:
    _init_test_db(tmp_path, "archive_legacy.db")
    asyncio.run(_seed_user("password:user@example.com", "user@example.com"))
    original, token = _configure_main_flags()
    try:
        async def _seed_legacy() -> None:
            async with database._session_factory() as session:  # type: ignore[union-attr]
                conv = Conversation(
                    user_id="password:user@example.com",
                    platform="web",
                    platform_chat_id="legacy-conv-1",
                    title="New web conversation",
                    status="active",
                )
                session.add(conv)
                await session.flush()
                session.add(ConversationMessage(conversation_id=conv.id, role="user", content="legacy msg", metadata_json=None))
                legacy_session = ChatSession(
                    user_id="password:user@example.com",
                    platform="web",
                    session_id="agent:main:web:legacy:conversation:legacy-conv-1",
                    title="Legacy session",
                    status="active",
                )
                session.add(legacy_session)
                await session.flush()
                session.add(ChatSessionMessage(session_ref_id=legacy_session.id, role="user", content="legacy session msg", metadata_json=None))
                await session.commit()

        asyncio.run(_seed_legacy())
        client = TestClient(main.app)
        client.cookies.set("aegis_session", token)
        response = client.get("/api/sessions")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        session_ids = [item["session_id"] for item in payload["sessions"]]
        assert session_ids == ["agent:main:main"]

        async def _assert_archived() -> None:
            async with database._session_factory() as session:  # type: ignore[union-attr]
                convs = (await session.execute(select(Conversation))).scalars().all()
                assert all(item.status == "archived" for item in convs)
                chat_sessions = (await session.execute(select(ChatSession))).scalars().all()
                assert any(item.session_id == "agent:main:main" and item.status == "active" for item in chat_sessions)
                assert any(item.session_id == "agent:main:web:legacy:conversation:legacy-conv-1" and item.status == "archived" for item in chat_sessions)
                archives = (await session.execute(select(LegacySessionArchive))).scalars().all()
                assert len(archives) == 2

        asyncio.run(_assert_archived())
    finally:
        _restore_main_flags(original)
