"""Admin conversation inspection endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.dependencies import get_admin_user
from backend.database import Conversation, ConversationMessage, User, get_session

router = APIRouter(
    prefix="/conversations",
    tags=["admin-conversations"],
    dependencies=[Depends(get_admin_user)],
)


def _serialize_datetime(value: datetime | None) -> str | None:
    """Serialize a datetime defensively for JSON responses."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _decode_metadata(metadata_json: str | None) -> dict[str, Any] | list[Any] | str | None:
    """Decode conversation metadata JSON when possible."""
    if not metadata_json:
        return None
    try:
        return json.loads(metadata_json)
    except json.JSONDecodeError:
        return metadata_json


def _escape_like_term(value: str) -> str:
    """Escape SQL LIKE wildcard characters in a search term."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _conversation_payload(
    conversation: Conversation,
    *,
    message_count: int,
) -> dict[str, Any]:
    """Convert a conversation row to a response payload."""
    return {
        "id": conversation.id,
        "user_id": conversation.user_id,
        "platform": conversation.platform,
        "platform_chat_id": conversation.platform_chat_id,
        "title": conversation.title,
        "status": conversation.status,
        "message_count": int(message_count),
        "created_at": _serialize_datetime(conversation.created_at),
        "updated_at": _serialize_datetime(conversation.updated_at),
    }


def _message_payload(message: ConversationMessage) -> dict[str, Any]:
    """Convert a conversation message row to a response payload."""
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "platform_message_id": message.platform_message_id,
        "metadata": _decode_metadata(message.metadata_json),
        "created_at": _serialize_datetime(message.created_at),
    }


def _conversation_filters(
    *,
    user_id: str | None,
    platform: str | None,
    status: str | None,
    search: str | None,
) -> list[Any]:
    """Build reusable SQLAlchemy filters for admin conversation queries."""
    filters: list[Any] = []

    if user_id:
        filters.append(Conversation.user_id == user_id)
    if platform:
        filters.append(Conversation.platform == platform)
    if status:
        filters.append(Conversation.status == status)
    if search:
        normalized_search = search.strip()
        if normalized_search:
            needle = f"%{_escape_like_term(normalized_search)}%"
            filters.append(
                or_(
                    Conversation.id.ilike(needle, escape="\\"),
                    Conversation.title.ilike(needle, escape="\\"),
                    Conversation.platform.ilike(needle, escape="\\"),
                    Conversation.platform_chat_id.ilike(needle, escape="\\"),
                    Conversation.user_id.ilike(needle, escape="\\"),
                    User.email.ilike(needle, escape="\\"),
                    User.name.ilike(needle, escape="\\"),
                )
            )

    return filters


async def _list_conversations(
    session: AsyncSession,
    *,
    user_id: str | None,
    platform: str | None,
    status: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Return paginated admin conversation results with message counts."""
    filters = _conversation_filters(
        user_id=user_id,
        platform=platform,
        status=status,
        search=search,
    )

    total_stmt = (
        select(func.count(distinct(Conversation.id)))
        .select_from(Conversation)
        .outerjoin(User, User.uid == Conversation.user_id)
    )
    if filters:
        total_stmt = total_stmt.where(and_(*filters))
    total = int((await session.scalar(total_stmt)) or 0)

    message_counts = (
        select(
            ConversationMessage.conversation_id.label("conversation_id"),
            func.count(ConversationMessage.id).label("message_count"),
        )
        .group_by(ConversationMessage.conversation_id)
        .subquery()
    )

    list_stmt = (
        select(
            Conversation,
            func.coalesce(message_counts.c.message_count, 0).label("message_count"),
        )
        .select_from(Conversation)
        .outerjoin(User, User.uid == Conversation.user_id)
        .outerjoin(message_counts, message_counts.c.conversation_id == Conversation.id)
        .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if filters:
        list_stmt = list_stmt.where(and_(*filters))

    rows = (await session.execute(list_stmt)).all()
    conversations = [
        _conversation_payload(conversation, message_count=message_count)
        for conversation, message_count in rows
    ]
    return {"conversations": conversations, "total": total}


@router.get("/stats")
async def get_conversation_stats(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return aggregate admin conversation stats grouped by platform."""
    stmt = (
        select(
            Conversation.platform,
            func.count(distinct(Conversation.id)).label("conversation_count"),
            func.count(ConversationMessage.id).label("message_count"),
            func.count(distinct(Conversation.user_id)).label("unique_user_count"),
        )
        .select_from(Conversation)
        .outerjoin(
            ConversationMessage,
            ConversationMessage.conversation_id == Conversation.id,
        )
        .group_by(Conversation.platform)
        .order_by(Conversation.platform.asc())
    )
    rows = (await session.execute(stmt)).all()
    return {
        "platforms": [
            {
                "platform": platform,
                "conversations": int(conversation_count or 0),
                "messages": int(message_count or 0),
                "unique_users": int(unique_user_count or 0),
            }
            for platform, conversation_count, message_count, unique_user_count in rows
        ]
    }


@router.get("/")
async def list_conversations(
    user_id: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List conversations for the admin surface."""
    return await _list_conversations(
        session,
        user_id=user_id,
        platform=platform,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/user/{uid}")
async def list_user_conversations(
    uid: str,
    platform: str | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List conversations for one specific user in the standard admin shape."""
    return await _list_conversations(
        session,
        user_id=uid,
        platform=platform,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/{conversation_id}")
async def get_conversation_detail(
    conversation_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return one conversation plus paginated messages for admins."""
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    message_total_stmt = select(func.count(ConversationMessage.id)).where(
        ConversationMessage.conversation_id == conversation_id
    )
    message_total = int((await session.scalar(message_total_stmt)) or 0)

    message_rows = (
        await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    return {
        "conversation": _conversation_payload(conversation, message_count=message_total),
        "messages": [_message_payload(message) for message in message_rows],
        "total": message_total,
        "limit": limit,
        "offset": offset,
    }
