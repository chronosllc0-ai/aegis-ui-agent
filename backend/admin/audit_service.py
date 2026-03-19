"""Helpers for persisting admin audit records."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AuditLog


async def log_admin_action(
    session: AsyncSession,
    *,
    admin_id: str,
    action: str,
    target_user_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Insert and commit an immutable admin audit log entry."""
    audit_log = AuditLog(
        admin_id=admin_id,
        action=action,
        target_user_id=target_user_id,
        details_json=json.dumps(details) if details is not None else None,
        ip_address=ip_address,
    )
    session.add(audit_log)
    session.add(audit_log)
    return audit_log
    await session.refresh(audit_log)
    return audit_log
