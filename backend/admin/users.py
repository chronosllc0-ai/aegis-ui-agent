"""Admin user management API endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.audit_service import log_admin_action
from backend.admin.dependencies import get_admin_user, require_superadmin
from backend.database import Conversation, CreditBalance, UsageEvent, User, get_session

router = APIRouter(dependencies=[Depends(get_admin_user)])

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
SORTABLE_USER_COLUMNS: dict[str, Any] = {
    "created_at": User.created_at,
    "email": User.email,
    "name": User.name,
    "role": User.role,
    "status": User.status,
    "last_login_at": User.last_login_at,
}


class UserUpdateRequest(BaseModel):
    """Mutable admin-managed user profile fields."""

    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    role: str | None = Field(default=None, max_length=20)


class UserRoleUpdateRequest(BaseModel):
    """Payload for updating a user's role."""

    role: str = Field(..., min_length=1, max_length=20)


class CreditAdjustmentRequest(BaseModel):
    """Payload for manually adjusting a user's credit consumption."""

    amount: int
    reason: str = Field(..., min_length=1, max_length=1000)


class SuspendActionRequest(BaseModel):
    """Optional reason payload for suspension status changes."""

    reason: str | None = Field(default=None, max_length=1000)


class UserRead(BaseModel):
    """Serialized user record."""

    model_config = ConfigDict(from_attributes=True)

    uid: str
    provider: str | None
    provider_id: str | None
    email: str | None
    name: str | None
    avatar_url: str | None
    role: str | None
    status: str | None
    created_at: datetime | None
    last_login_at: datetime | None


async def _get_user_or_404(session: AsyncSession, uid: str) -> User:
    """Load a user or raise a 404."""
    user = await session.get(User, uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _get_or_create_balance(session: AsyncSession, uid: str) -> CreditBalance:
    """Load or create a credit balance record for the target user."""
    result = await session.execute(
        select(CreditBalance).where(CreditBalance.user_id == uid)
    )
    balance = result.scalar_one_or_none()
    if balance:
        return balance

    now = datetime.now(timezone.utc)
    cycle_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (cycle_start + timedelta(days=32)).replace(day=1)
    balance = CreditBalance(
        id=str(uuid4()),
        user_id=uid,
        plan="free",
        monthly_allowance=1000,
        credits_used=0,
        overage_credits=0,
        cycle_start=cycle_start,
        cycle_end=next_month - timedelta(seconds=1),
    )
    session.add(balance)
    await session.flush()
    return balance


@router.get("/")
async def list_users(
    session: AsyncSession = Depends(get_session),
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return a filtered and paginated admin user list."""
    sort_column = SORTABLE_USER_COLUMNS.get(sort_by)
    if sort_column is None:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Invalid sort_by value",
                "allowed": sorted(SORTABLE_USER_COLUMNS),
            },
        )

    normalized_sort_dir = sort_dir.lower()
    if normalized_sort_dir not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="Invalid sort_dir value")

    filters = []
    if search:
        search_term = f"%{search.strip().lower()}%"
        if search_term != "%%":
            filters.append(
                or_(
                    func.lower(func.coalesce(User.email, "")).like(search_term),
                    func.lower(func.coalesce(User.name, "")).like(search_term),
                )
            )
    if role:
        filters.append(User.role == role)
    if status:
        filters.append(User.status == status)

    base_query = select(User)
    total_query = select(func.count()).select_from(User)
    for query_filter in filters:
        base_query = base_query.where(query_filter)
        total_query = total_query.where(query_filter)

    order_clause = sort_column.asc() if normalized_sort_dir == "asc" else sort_column.desc()
    user_query = base_query.order_by(order_clause, User.uid.asc()).offset(offset).limit(limit)

    total = int((await session.execute(total_query)).scalar_one())
    users = (await session.execute(user_query)).scalars().all()

    return {
        "users": [UserRead.model_validate(user).model_dump(mode="json") for user in users],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{uid}")
async def get_user_detail(
    uid: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return a detailed admin view of a user and related usage data."""
    user = await _get_user_or_404(session, uid)

    balance_result = await session.execute(
        select(CreditBalance).where(CreditBalance.user_id == uid)
    )
    balance = balance_result.scalar_one_or_none()

    conversation_total = int(
        (
            await session.execute(
                select(func.count()).select_from(Conversation).where(Conversation.user_id == uid)
            )
        ).scalar_one()
    )

    usage_totals_row = (
        await session.execute(
            select(
                func.coalesce(func.sum(UsageEvent.credits_charged), 0).label("total_credits"),
                func.coalesce(func.sum(UsageEvent.credits_used), 0.0).label("total_exact_credits"),
                func.count(UsageEvent.id).label("event_count"),
            ).where(UsageEvent.user_id == uid)
        )
    ).one()

    top_models_rows = (
        await session.execute(
            select(
                UsageEvent.provider,
                UsageEvent.model,
                func.count(UsageEvent.id).label("event_count"),
                func.coalesce(func.sum(UsageEvent.credits_charged), 0).label("total_credits"),
            )
            .where(UsageEvent.user_id == uid)
            .group_by(UsageEvent.provider, UsageEvent.model)
            .order_by(func.sum(UsageEvent.credits_charged).desc(), func.count(UsageEvent.id).desc())
            .limit(5)
        )
    ).all()

    return {
        "user": UserRead.model_validate(user).model_dump(mode="json"),
        "credit_balance": {
            "id": balance.id,
            "user_id": balance.user_id,
            "plan": balance.plan,
            "monthly_allowance": balance.monthly_allowance,
            "credits_used": balance.credits_used,
            "overage_credits": balance.overage_credits,
            "cycle_start": balance.cycle_start.isoformat() if balance.cycle_start else None,
            "cycle_end": balance.cycle_end.isoformat() if balance.cycle_end else None,
            "spending_cap": balance.spending_cap,
            "updated_at": balance.updated_at.isoformat() if balance.updated_at else None,
        }
        if balance
        else None,
        "conversation_count": conversation_total,
        "usage_summary": {
            "total_credits": int(usage_totals_row.total_credits or 0),
            "total_exact_credits": float(usage_totals_row.total_exact_credits or 0.0),
            "event_count": int(usage_totals_row.event_count or 0),
            "top_models": [
                {
                    "provider": row.provider,
                    "model": row.model,
                    "event_count": int(row.event_count or 0),
                    "total_credits": int(row.total_credits or 0),
                }
                for row in top_models_rows
            ],
        },
    }


@router.put("/{uid}")
async def update_user_profile(
    uid: str,
    payload: UserUpdateRequest,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update mutable profile fields for a user."""
    user = await _get_user_or_404(session, uid)
    before = UserRead.model_validate(user).model_dump(mode="json")

    update_data = payload.model_dump(exclude_unset=True)
    role_update = update_data.pop("role", None)
    if role_update is not None:
        await require_superadmin(admin_user)
        user.role = role_update

    for field_name, value in update_data.items():
        setattr(user, field_name, value)

    await log_admin_action(
        session,
        admin_id=admin_user.uid,
        action="update_user_profile",
        target_user_id=user.uid,
        details={
            "before": before,
            "after": UserRead.model_validate(user).model_dump(mode="json"),
        },
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    await session.refresh(user)

    return {"user": UserRead.model_validate(user).model_dump(mode="json")}


@router.put("/{uid}/role")
async def update_user_role(
    uid: str,
    payload: UserRoleUpdateRequest,
    request: Request,
    admin_user: User = Depends(require_superadmin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update a user's role using a superadmin-only route."""
    user = await _get_user_or_404(session, uid)
    before_role = user.role
    user.role = payload.role

    await log_admin_action(
        session,
        admin_id=admin_user.uid,
        action="change_user_role",
        target_user_id=user.uid,
        details={"before": before_role, "after": payload.role},
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    await session.refresh(user)

    return {"user": UserRead.model_validate(user).model_dump(mode="json")}


@router.post("/{uid}/suspend")
async def suspend_user(
    uid: str,
    request: Request,
    payload: SuspendActionRequest | None = None,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Suspend a user account."""
    user = await _get_user_or_404(session, uid)
    before_status = user.status
    user.status = "suspended"

    await log_admin_action(
        session,
        admin_id=admin_user.uid,
        action="suspend_user",
        target_user_id=user.uid,
        details={
            "before": before_status,
            "after": user.status,
            "reason": payload.reason if payload else None,
        },
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    await session.refresh(user)

    return {"user": UserRead.model_validate(user).model_dump(mode="json")}


@router.post("/{uid}/reinstate")
async def reinstate_user(
    uid: str,
    request: Request,
    payload: SuspendActionRequest | None = None,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Reinstate a suspended user account."""
    user = await _get_user_or_404(session, uid)
    before_status = user.status
    user.status = "active"

    await log_admin_action(
        session,
        admin_id=admin_user.uid,
        action="reinstate_user",
        target_user_id=user.uid,
        details={
            "before": before_status,
            "after": user.status,
            "reason": payload.reason if payload else None,
        },
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    await session.refresh(user)

    return {"user": UserRead.model_validate(user).model_dump(mode="json")}


@router.post("/{uid}/credit-adjustment")
async def adjust_user_credits(
    uid: str,
    payload: CreditAdjustmentRequest,
    request: Request,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Apply a manual credit adjustment by shifting the recorded credits used."""
    await _get_user_or_404(session, uid)
    balance = await _get_or_create_balance(session, uid)

    before = {
        "credits_used": balance.credits_used,
        "overage_credits": balance.overage_credits,
    }

    if payload.amount >= 0:
        reduction_remaining = payload.amount
        applied_to_overage = min(balance.overage_credits, reduction_remaining)
        balance.overage_credits -= applied_to_overage
        reduction_remaining -= applied_to_overage
        applied_to_usage = min(balance.credits_used, reduction_remaining)
        balance.credits_used -= applied_to_usage
        applied_amount = applied_to_overage + applied_to_usage
    else:
        increase_amount = abs(payload.amount)
        remaining_in_plan = max(balance.monthly_allowance - balance.credits_used, 0)
        applied_to_usage = min(remaining_in_plan, increase_amount)
        balance.credits_used += applied_to_usage
        applied_to_overage = increase_amount - applied_to_usage
        balance.overage_credits += applied_to_overage
        applied_amount = -(applied_to_usage + applied_to_overage)

    balance.credits_used = max(0, min(balance.credits_used, balance.monthly_allowance))
    balance.overage_credits = max(0, balance.overage_credits)

    after = {
        "credits_used": balance.credits_used,
        "overage_credits": balance.overage_credits,
    }

    await log_admin_action(
        session,
        admin_id=admin_user.uid,
        action="credit_adjustment",
        target_user_id=uid,
        details={
            "amount": payload.amount,
            "applied_amount": applied_amount,
            "reason": payload.reason,
            "before": before,
            "after": after,
        },
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    await session.refresh(balance)

    return {
        "credit_balance": {
            "id": balance.id,
            "user_id": balance.user_id,
            "plan": balance.plan,
            "monthly_allowance": balance.monthly_allowance,
            "credits_used": balance.credits_used,
            "overage_credits": balance.overage_credits,
            "cycle_start": balance.cycle_start.isoformat() if balance.cycle_start else None,
            "cycle_end": balance.cycle_end.isoformat() if balance.cycle_end else None,
            "spending_cap": balance.spending_cap,
            "updated_at": balance.updated_at.isoformat() if balance.updated_at else None,
        },
        "adjustment": {
            "requested_amount": payload.amount,
            "applied_amount": applied_amount,
            "reason": payload.reason,
        },
    }
