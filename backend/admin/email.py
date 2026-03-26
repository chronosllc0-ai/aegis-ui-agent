"""Admin email broadcast endpoint.

POST /api/admin/email/send
  body: { user_ids: string[] | "all", subject: string, body: string }
  Returns: { sent: number, failed: number }
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Union

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.dependencies import get_admin_user
from backend.database import User, get_session
from backend.email_service import send_custom_email

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_admin_user)])


class EmailBroadcastPayload(BaseModel):
    user_ids: Union[list[str], str]  # list of UIDs or "all"
    subject: str
    body: str
    from_address: str | None = None  # e.g. "Jesse <jesse@mohex.org>"


@router.post("/send")
async def send_admin_email(
    payload: EmailBroadcastPayload,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Send an email to one or more users (or all active users)."""
    subject = payload.subject.strip()
    body = payload.body.strip()
    from_address = (payload.from_address or "").strip() or None

    if not subject:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="subject is required")
    if not body:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="body is required")

    # Resolve recipient list
    if payload.user_ids == "all":
        result = await session.execute(
            select(User).where(User.status == "active", User.email.isnot(None))
        )
        users = result.scalars().all()
    else:
        if not isinstance(payload.user_ids, list) or len(payload.user_ids) == 0:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="user_ids must be 'all' or a non-empty list")
        result = await session.execute(
            select(User).where(User.uid.in_(payload.user_ids), User.email.isnot(None))
        )
        users = result.scalars().all()

    if not users:
        return {"sent": 0, "failed": 0}

    sent = 0
    failed = 0
    first_error: str | None = None

    async def _send_one(user: User) -> None:
        nonlocal sent, failed, first_error
        try:
            await send_custom_email(user.email, subject, body, from_address=from_address)  # type: ignore[arg-type]
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send admin email to %s: %s", user.email, exc)
            failed += 1
            if first_error is None:
                first_error = str(exc)

    # Send concurrently (Resend API handles rate limiting gracefully)
    await asyncio.gather(*[_send_one(u) for u in users])

    logger.info("Admin email broadcast: sent=%d, failed=%d, subject=%r", sent, failed, subject)

    # If every single send failed, surface the error so the admin knows why
    if failed > 0 and sent == 0 and first_error:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=first_error)

    return {"sent": sent, "failed": failed}
