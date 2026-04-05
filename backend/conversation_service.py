"""Conversation persistence helpers.

These helpers are intentionally small so websocket and integration handlers
can log messages without knowing database details.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Conversation, ConversationMessage

PLACEHOLDER_TITLES = {"new task", "untitled", ""}


def _normalize_title(value: str | None) -> str:
    return (value or "").strip()


def _is_placeholder_title(value: str | None) -> bool:
    return _normalize_title(value).lower() in PLACEHOLDER_TITLES


def _derive_title_from_instruction(text: str, limit: int = 120) -> str:
    clean = " ".join((text or "").split()).strip()
    return clean[:limit] if clean else "New task"


async def get_or_create_conversation(
    session: AsyncSession,
    user_id: str,
    platform: str,
    platform_chat_id: str | None = None,
    title: str | None = None,
) -> Conversation:
    """Return the latest active conversation for a user/platform/chat tuple."""
    query = (
        select(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.platform == platform,
            Conversation.status == "active",
        )
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    if platform_chat_id is not None:
        query = query.where(Conversation.platform_chat_id == platform_chat_id)

    existing = (await session.execute(query)).scalar_one_or_none()
    if existing is not None:
        return existing

    now = datetime.now(timezone.utc)
    conversation = Conversation(
        id=str(uuid4()),
        user_id=user_id,
        platform=platform,
        platform_chat_id=platform_chat_id,
        title=(title or f"New {platform} conversation")[:500],
        status="active",
        updated_at=now,
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def append_message(
    session: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict[str, object] | None = None,
    platform_message_id: str | None = None,
    title_candidate: str | None = None,
) -> ConversationMessage | None:
    """Persist a conversation message and bump the parent conversation timestamp."""
    normalized = content.strip()
    if not normalized:
        return None

    message = ConversationMessage(
        id=str(uuid4()),
        conversation_id=conversation_id,
        role=role,
        content=normalized,
        platform_message_id=platform_message_id,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    session.add(message)

    conversation = await session.get(Conversation, conversation_id)
    if conversation is not None:
        if role == "user" and _is_placeholder_title(conversation.title):
            metadata_task_label = metadata.get("task_label") if metadata else None
            preferred = metadata_task_label if isinstance(metadata_task_label, str) else None
            if _is_placeholder_title(preferred):
                preferred = title_candidate
            if _is_placeholder_title(preferred):
                preferred = normalized
            conversation.title = _derive_title_from_instruction(preferred)[:500]
        conversation.updated_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(message)
    return message


async def update_conversation_title(
    session: AsyncSession,
    conversation_id: str,
    title: str,
) -> None:
    """Update a conversation title when a better first-user summary becomes available."""
    normalized = title.strip()
    if not normalized:
        return

    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        return

    conversation.title = normalized[:500]
    conversation.updated_at = datetime.now(timezone.utc)
    await session.commit()
