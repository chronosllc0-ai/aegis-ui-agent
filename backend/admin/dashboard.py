"""Admin dashboard statistics."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.dependencies import get_admin_user
from backend.database import AuditLog, Conversation, UsageEvent, User, get_session

router = APIRouter()


def _decode_details(details_json: str | None) -> dict[str, Any] | list[Any] | None:
    """Safely decode JSON audit log details."""
    if not details_json:
        return None
    try:
        return json.loads(details_json)
    except json.JSONDecodeError:
        return None


@router.get("/")
async def dashboard_stats(
    admin: dict = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return overview statistics for the admin dashboard."""
    _ = admin
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_users = (
        await session.scalar(select(func.count(User.uid)))
    ) or 0
    active_users = (
        await session.scalar(
            select(func.count(User.uid)).where(User.last_login_at >= week_ago)
        )
    ) or 0
    new_users_this_month = (
        await session.scalar(
            select(func.count(User.uid)).where(User.created_at >= month_start)
        )
    ) or 0
    credits_used_this_month = (
        await session.scalar(
            select(func.coalesce(func.sum(UsageEvent.credits_charged), 0)).where(
                UsageEvent.created_at >= month_start
            )
        )
    ) or 0
    active_conversations = (
        await session.scalar(
            select(func.count(Conversation.id)).where(Conversation.status == "active")
        )
    ) or 0

    platform_rows = (
        await session.execute(
            select(Conversation.platform, func.count(Conversation.id))
            .group_by(Conversation.platform)
            .order_by(Conversation.platform.asc())
        )
    ).all()
    platform_breakdown = {platform: count for platform, count in platform_rows}

    recent_audit_rows = (
        await session.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(10)
        )
    ).scalars().all()
    recent_activity = [
        {
            "id": entry.id,
            "admin_id": entry.admin_id,
            "action": entry.action,
            "target_user_id": entry.target_user_id,
            "details": _decode_details(entry.details_json),
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        for entry in recent_audit_rows
    ]

    return {
        "total_users": total_users,
        "active_users": active_users,
        "new_users_this_month": new_users_this_month,
        "credits_used_this_month": credits_used_this_month,
        "active_conversations": active_conversations,
        "platform_breakdown": platform_breakdown,
        "recent_activity": recent_activity,
    }
