"""Admin audit log listing endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.dependencies import get_admin_user
from backend.database import AuditLog, User, get_session

router = APIRouter(dependencies=[Depends(get_admin_user)])

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _parse_iso_datetime(value: str, *, field_name: str) -> datetime:
    """Parse an ISO-8601 datetime string and normalize naive values to UTC."""
    normalized_value = value.strip()
    if not normalized_value:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} timestamp")

    if normalized_value.endswith("Z"):
        normalized_value = f"{normalized_value[:-1]}+00:00"

    try:
        parsed_value = datetime.fromisoformat(normalized_value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} timestamp") from exc

    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=timezone.utc)
    return parsed_value


def _decode_details(details_json: str | None) -> dict[str, Any] | list[Any] | str | None:
    """Safely decode historic audit detail payloads without failing the endpoint."""
    if not details_json:
        return None
    try:
        return json.loads(details_json)
    except (TypeError, json.JSONDecodeError):
        return details_json


def _serialize_entry(entry: AuditLog) -> dict[str, Any]:
    """Return a JSON-friendly audit log payload."""
    return {
        "id": entry.id,
        "admin_id": entry.admin_id,
        "action": entry.action,
        "target_user_id": entry.target_user_id,
        "details": _decode_details(entry.details_json),
        "ip_address": entry.ip_address,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


@router.get("/")
async def list_audit_entries(
    admin_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    target_user_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return filtered and paginated admin audit log entries."""
    filters = []

    if admin_id:
        filters.append(AuditLog.admin_id == admin_id)
    if action:
        filters.append(AuditLog.action == action)
    if target_user_id:
        filters.append(AuditLog.target_user_id == target_user_id)
    if date_from:
        filters.append(AuditLog.created_at >= _parse_iso_datetime(date_from, field_name="date_from"))
    if date_to:
        filters.append(AuditLog.created_at <= _parse_iso_datetime(date_to, field_name="date_to"))

    entries_query = select(AuditLog)
    total_query = select(func.count()).select_from(AuditLog)
    for audit_filter in filters:
        entries_query = entries_query.where(audit_filter)
        total_query = total_query.where(audit_filter)

    entries_query = (
        entries_query.order_by(nulls_last(AuditLog.created_at.desc()), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    )

    total = int((await session.execute(total_query)).scalar_one())
    entries = (await session.execute(entries_query)).scalars().all()
    return {"entries": [_serialize_entry(entry) for entry in entries], "total": total}
