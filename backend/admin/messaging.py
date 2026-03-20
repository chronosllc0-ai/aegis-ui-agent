"""Admin messaging dashboard — view and reply to customer support threads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import SupportMessage, SupportThread, User, get_session
from .dependencies import get_admin_user

router = APIRouter(tags=["admin-messaging"])


class AdminReplyBody(BaseModel):
    content: str


class UpdateThreadBody(BaseModel):
    status: str | None = None
    priority: str | None = None


@router.get("/threads")
async def list_threads(
    status: str | None = None,
    db: AsyncSession = Depends(get_session),
    _admin: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """List all support threads (newest first), with optional status filter."""
    q = select(SupportThread).order_by(SupportThread.updated_at.desc())
    if status:
        q = q.where(SupportThread.status == status)
    result = await db.execute(q)
    threads = result.scalars().all()

    items: list[dict[str, Any]] = []
    for t in threads:
        user_row = await db.execute(select(User).where(User.uid == t.user_id))
        user = user_row.scalar_one_or_none()
        msg_count = (await db.execute(select(func.count()).select_from(SupportMessage).where(SupportMessage.thread_id == t.id))).scalar() or 0
        last_msg = (await db.execute(
            select(SupportMessage).where(SupportMessage.thread_id == t.id).order_by(SupportMessage.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        items.append({
            "id": t.id,
            "subject": t.subject,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            "message_count": msg_count,
            "last_message": last_msg.content[:120] if last_msg else None,
            "last_message_at": last_msg.created_at.isoformat() if last_msg and last_msg.created_at else None,
            "user": {
                "uid": user.uid,
                "name": user.name,
                "email": user.email,
                "avatar_url": user.avatar_url,
            } if user else None,
        })
    return {"threads": items, "total": len(items)}


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_session),
    _admin: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """Get a single support thread with all its messages."""
    result = await db.execute(select(SupportThread).where(SupportThread.id == thread_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(404, "Thread not found")

    user_row = await db.execute(select(User).where(User.uid == thread.user_id))
    user = user_row.scalar_one_or_none()

    msgs_result = await db.execute(
        select(SupportMessage).where(SupportMessage.thread_id == thread_id).order_by(SupportMessage.created_at.asc())
    )
    messages = msgs_result.scalars().all()

    sender_ids = {m.sender_id for m in messages}
    sender_map: dict[str, dict[str, Any]] = {}
    for sid in sender_ids:
        u = (await db.execute(select(User).where(User.uid == sid))).scalar_one_or_none()
        if u:
            sender_map[sid] = {"uid": u.uid, "name": u.name, "avatar_url": u.avatar_url, "role": u.role}

    return {
        "thread": {
            "id": thread.id,
            "subject": thread.subject,
            "status": thread.status,
            "priority": thread.priority,
            "created_at": thread.created_at.isoformat() if thread.created_at else None,
            "user": {
                "uid": user.uid,
                "name": user.name,
                "email": user.email,
                "avatar_url": user.avatar_url,
            } if user else None,
        },
        "messages": [
            {
                "id": m.id,
                "sender_id": m.sender_id,
                "sender_role": m.sender_role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "sender": sender_map.get(m.sender_id),
            }
            for m in messages
        ],
    }


@router.post("/threads/{thread_id}/reply")
async def admin_reply(
    thread_id: str,
    body: AdminReplyBody,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """Admin sends a reply to a support thread."""
    result = await db.execute(select(SupportThread).where(SupportThread.id == thread_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(404, "Thread not found")

    msg = SupportMessage(
        thread_id=thread_id,
        sender_id=admin.uid,
        sender_role="admin",
        content=body.content.strip(),
    )
    db.add(msg)
    thread.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(msg)

    return {
        "message": {
            "id": msg.id,
            "sender_id": msg.sender_id,
            "sender_role": "admin",
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }
    }


@router.patch("/threads/{thread_id}")
async def update_thread(
    thread_id: str,
    body: UpdateThreadBody,
    db: AsyncSession = Depends(get_session),
    _admin: User = Depends(get_admin_user),
) -> dict[str, str]:
    """Update thread status or priority."""
    result = await db.execute(select(SupportThread).where(SupportThread.id == thread_id))
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(404, "Thread not found")

    if body.status and body.status in ("open", "resolved", "closed"):
        thread.status = body.status
    if body.priority and body.priority in ("low", "normal", "high", "urgent"):
        thread.priority = body.priority
    thread.updated_at = datetime.utcnow()
    await db.commit()
    return {"status": "updated"}
