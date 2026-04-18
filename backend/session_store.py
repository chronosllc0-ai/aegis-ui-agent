"""Session-v2 persistence helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import ChatSession, ChatSessionMessage


async def get_or_create_session(
    db: AsyncSession,
    *,
    user_id: str,
    platform: str,
    session_id: str,
    title: str | None = None,
    parent_session_id: str | None = None,
) -> ChatSession:
    """Resolve an existing session-v2 row or create a new one."""
    stmt = select(ChatSession).where(
        ChatSession.user_id == user_id,
        ChatSession.platform == platform,
        ChatSession.session_id == session_id,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    row = ChatSession(
        id=str(uuid4()),
        user_id=user_id,
        platform=platform,
        session_id=session_id,
        parent_session_id=parent_session_id,
        title=(title or "New session")[:500],
        status="active",
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return row


async def append_session_message(
    db: AsyncSession,
    *,
    session_ref_id: str,
    role: str,
    content: str,
    metadata: dict[str, object] | None = None,
) -> ChatSessionMessage | None:
    """Append a non-empty session-v2 message and update the parent timestamp."""
    normalized = str(content or "").strip()
    if not normalized:
        return None
    row = ChatSessionMessage(
        id=str(uuid4()),
        session_ref_id=session_ref_id,
        role=role,
        content=normalized,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(row)
    session_row = await db.get(ChatSession, session_ref_id)
    if session_row is not None:
        session_row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return row
