"""Sessions-first migration helpers.

Archives legacy conversation/task UI records, hides them from active listings,
and ensures each user has a persistent main session.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import (
    ChatSession,
    ChatSessionMessage,
    Conversation,
    ConversationMessage,
    LegacySessionArchive,
)
from backend.session_identity import SESSION_MAIN_ID
from backend.session_store import get_or_create_session


async def migrate_user_to_sessions_first(
    db: AsyncSession,
    *,
    user_id: str,
    platform: str = "web",
) -> dict[str, int | str]:
    """Archive legacy UI history for a user and ensure the main session exists."""
    archived_conversations = await _archive_legacy_conversations(db, user_id=user_id, platform=platform)
    archived_sessions = await _archive_legacy_sessions(db, user_id=user_id, platform=platform)

    await get_or_create_session(
        db,
        user_id=user_id,
        platform=platform,
        session_id=SESSION_MAIN_ID,
        title="Main session",
    )
    await db.commit()

    return {
        "user_id": user_id,
        "archived_conversations": archived_conversations,
        "archived_sessions": archived_sessions,
        "main_session_id": SESSION_MAIN_ID,
    }


async def _archive_legacy_conversations(db: AsyncSession, *, user_id: str, platform: str) -> int:
    rows = (
        await db.execute(
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.platform == platform,
                Conversation.status != "archived",
            )
            .order_by(Conversation.updated_at.desc())
        )
    ).scalars().all()
    archived = 0
    for row in rows:
        key = f"conversation:{row.id}"
        if await _archive_exists(db, archive_key=key):
            row.status = "archived"
            continue
        messages = (
            await db.execute(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == row.id)
                .order_by(ConversationMessage.created_at.asc())
            )
        ).scalars().all()
        payload = {
            "conversation": {
                "id": row.id,
                "platform_chat_id": row.platform_chat_id,
                "title": row.title,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            },
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "metadata_json": m.metadata_json,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
        }
        db.add(
            LegacySessionArchive(
                id=str(uuid4()),
                user_id=user_id,
                platform=platform,
                archive_key=key,
                source_type="conversation",
                source_id=row.id,
                payload_json=json.dumps(payload),
                archived_at=datetime.now(timezone.utc),
            )
        )
        row.status = "archived"
        archived += 1
    return archived


async def _archive_legacy_sessions(db: AsyncSession, *, user_id: str, platform: str) -> int:
    rows = (
        await db.execute(
            select(ChatSession)
            .where(
                ChatSession.user_id == user_id,
                ChatSession.platform == platform,
                ChatSession.status != "archived",
                ChatSession.session_id != SESSION_MAIN_ID,
            )
            .order_by(ChatSession.updated_at.desc())
        )
    ).scalars().all()
    archived = 0
    for row in rows:
        key = f"chat_session:{row.id}"
        if await _archive_exists(db, archive_key=key):
            row.status = "archived"
            continue
        messages = (
            await db.execute(
                select(ChatSessionMessage)
                .where(ChatSessionMessage.session_ref_id == row.id)
                .order_by(ChatSessionMessage.created_at.asc())
            )
        ).scalars().all()
        payload = {
            "chat_session": {
                "id": row.id,
                "session_id": row.session_id,
                "parent_session_id": row.parent_session_id,
                "title": row.title,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            },
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "metadata_json": m.metadata_json,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
        }
        db.add(
            LegacySessionArchive(
                id=str(uuid4()),
                user_id=user_id,
                platform=platform,
                archive_key=key,
                source_type="chat_session",
                source_id=row.id,
                payload_json=json.dumps(payload),
                archived_at=datetime.now(timezone.utc),
            )
        )
        row.status = "archived"
        archived += 1
    return archived


async def _archive_exists(db: AsyncSession, *, archive_key: str) -> bool:
    existing = (
        await db.execute(select(LegacySessionArchive.id).where(LegacySessionArchive.archive_key == archive_key))
    ).scalar_one_or_none()
    return existing is not None
