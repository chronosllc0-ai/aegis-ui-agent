"""Regression tests for first-user-message title promotion."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select

from backend import database
from backend.conversation_service import append_message, get_or_create_conversation
from backend.database import Conversation, User


def _init_test_db(tmp_path: Path, name: str) -> None:
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / name}")
    asyncio.run(database.create_tables())


async def _seed_user(uid: str, email: str, name: str = "Test User") -> None:
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


async def _fetch_conversation(conversation_id: str) -> Conversation:
    async with database._session_factory() as session:  # type: ignore[union-attr]
        return (
            await session.execute(select(Conversation).where(Conversation.id == conversation_id))
        ).scalar_one()


def test_first_user_message_promotes_placeholder_conversation_title(tmp_path: Path) -> None:
    _init_test_db(tmp_path, "conversation_title_promotion.db")
    asyncio.run(_seed_user("password:user@example.com", "user@example.com"))

    async def _run() -> None:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            conversation = await get_or_create_conversation(
                session,
                user_id="password:user@example.com",
                platform="web",
                platform_chat_id="ws-1",
                title="New task",
            )
            original_updated_at = conversation.updated_at

            await append_message(
                session,
                conversation.id,
                "user",
                "Find wireless headphones under $50",
                metadata={"source": "test", "task_label": "New task"},
                title_candidate="Find wireless headphones under $50",
            )

            promoted = await _fetch_conversation(conversation.id)
            assert promoted.title == "Find wireless headphones under $50"
            assert promoted.updated_at is not None
            if original_updated_at is not None:
                assert promoted.updated_at >= original_updated_at

            await append_message(
                session,
                conversation.id,
                "user",
                "Sort by highest rating",
                metadata={"source": "test"},
                title_candidate="Sort by highest rating",
            )

            after_second = await _fetch_conversation(conversation.id)
            assert after_second.title == "Find wireless headphones under $50"

    asyncio.run(_run())
