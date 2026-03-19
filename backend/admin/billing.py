"""Admin billing management routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.audit_service import log_admin_action
from backend.admin.dependencies import get_admin_user
from backend.credit_service import get_or_create_balance
from backend.database import CreditBalance, PaymentMethod, User, get_session

_CURRENT_YEAR = datetime.now(timezone.utc).year

router = APIRouter(dependencies=[Depends(get_admin_user)])


class PaymentMethodCreate(BaseModel):
    """Payload for creating a payment method."""

    type: str = Field(min_length=1, max_length=30)
    brand: str = Field(min_length=1, max_length=30)
    last4: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=_CURRENT_YEAR)


class PlanUpdate(BaseModel):
    """Payload for updating a user's billing plan."""

    plan: str = Field(min_length=1, max_length=50)
    monthly_allowance: int = Field(ge=0)


async def _get_target_user(session: AsyncSession, uid: str) -> User:
    """Load the target user or raise a 404."""
    user = await session.get(User, uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _get_user_payment_methods_for_update(
    session: AsyncSession,
    uid: str,
) -> list[PaymentMethod]:
    """Lock and return a user's payment methods in deterministic order."""
    rows = await session.execute(
        select(PaymentMethod)
        .where(PaymentMethod.user_id == uid)
        .order_by(PaymentMethod.created_at.asc(), PaymentMethod.id.asc())
        .with_for_update()
    )
    return list(rows.scalars().all())


async def _get_locked_payment_method(
    session: AsyncSession,
    *,
    uid: str,
    pm_id: str,
) -> tuple[PaymentMethod, list[PaymentMethod]]:
    """Lock a user's payment methods and return the requested one."""
    payment_methods = await _get_user_payment_methods_for_update(session, uid)
    payment_method = next((method for method in payment_methods if method.id == pm_id), None)
    if payment_method is None:
        raise HTTPException(status_code=404, detail="Payment method not found")
    return payment_method, payment_methods


def _get_cycle_bounds(reference_time: datetime) -> tuple[datetime, datetime]:
    """Return the current billing cycle bounds for a UTC timestamp."""
    cycle_start = reference_time.astimezone(timezone.utc).replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    if cycle_start.month == 12:
        next_month = cycle_start.replace(year=cycle_start.year + 1, month=1)
    else:
        next_month = cycle_start.replace(month=cycle_start.month + 1)
    return cycle_start, next_month - timedelta(seconds=1)


def _serialize_payment_method(payment_method: PaymentMethod) -> dict[str, Any]:
    """Return a JSON-friendly payment method payload."""
    return {
        "id": payment_method.id,
        "user_id": payment_method.user_id,
        "type": payment_method.type,
        "brand": payment_method.brand,
        "last4": payment_method.last4,
        "exp_month": payment_method.exp_month,
        "exp_year": payment_method.exp_year,
        "is_default": bool(payment_method.is_default),
        "created_at": payment_method.created_at.isoformat() if payment_method.created_at else None,
    }


def _serialize_credit_balance(balance: CreditBalance) -> dict[str, Any]:
    """Return a JSON-friendly credit balance payload."""
    return {
        "id": balance.id,
        "user_id": balance.user_id,
        "plan": balance.plan,
        "monthly_allowance": balance.monthly_allowance,
        "credits_used": balance.credits_used,
        "overage_credits": balance.overage_credits,
        "spending_cap": balance.spending_cap,
        "cycle_start": balance.cycle_start.isoformat() if balance.cycle_start else None,
        "cycle_end": balance.cycle_end.isoformat() if balance.cycle_end else None,
        "updated_at": balance.updated_at.isoformat() if balance.updated_at else None,
    }


@router.get("/users/{uid}/payment-methods")
async def list_payment_methods(
    uid: str,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List saved payment methods for the target user."""
    await _get_target_user(session, uid)
    rows = await session.execute(
        select(PaymentMethod)
        .where(PaymentMethod.user_id == uid)
        .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.asc())
    )
    methods = rows.scalars().all()
    return {"user_id": uid, "payment_methods": [_serialize_payment_method(method) for method in methods]}


@router.post("/users/{uid}/payment-methods")
async def create_payment_method(
    uid: str,
    payload: PaymentMethodCreate,
    request: Request,
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a payment method for the target user."""
    await _get_target_user(session, uid)
    existing_methods = await _get_user_payment_methods_for_update(session, uid)
    has_default = any(method.is_default for method in existing_methods)

    payment_method = PaymentMethod(
        user_id=uid,
        type=payload.type,
        brand=payload.brand,
        last4=payload.last4,
        exp_month=payload.exp_month,
        exp_year=payload.exp_year,
        is_default=not has_default,
    )
    session.add(payment_method)
    await session.flush()
    await log_admin_action(
        session,
        admin_id=admin.uid,
        action="billing.add_payment_method",
        target_user_id=uid,
        details={
            "payment_method_id": payment_method.id,
            "type": payment_method.type,
            "brand": payment_method.brand,
            "last4": payment_method.last4,
            "exp_month": payment_method.exp_month,
            "exp_year": payment_method.exp_year,
            "is_default": payment_method.is_default,
        },
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    await session.refresh(payment_method)

    return _serialize_payment_method(payment_method)


@router.put("/users/{uid}/payment-methods/{pm_id}/default")
async def set_default_payment_method(
    uid: str,
    pm_id: str,
    request: Request,
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Set the selected payment method as the user's default."""
    await _get_target_user(session, uid)
    payment_method, payment_methods = await _get_locked_payment_method(session, uid=uid, pm_id=pm_id)

    for method in payment_methods:
        method.is_default = method.id == payment_method.id

    await session.flush()
    await log_admin_action(
        session,
        admin_id=admin.uid,
        action="billing.set_default_payment",
        target_user_id=uid,
        details={
            "payment_method_id": payment_method.id,
            "brand": payment_method.brand,
            "last4": payment_method.last4,
        },
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    await session.refresh(payment_method)
    return _serialize_payment_method(payment_method)


@router.delete("/users/{uid}/payment-methods/{pm_id}")
async def delete_payment_method(
    uid: str,
    pm_id: str,
    request: Request,
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Delete a payment method belonging to the target user."""
    await _get_target_user(session, uid)
    payment_method, payment_methods = await _get_locked_payment_method(session, uid=uid, pm_id=pm_id)
    deleted_payload = _serialize_payment_method(payment_method)
    deleted_was_default = bool(payment_method.is_default)

    remaining_methods = [method for method in payment_methods if method.id != payment_method.id]
    promoted_method = remaining_methods[0] if deleted_was_default and remaining_methods else None
    for method in remaining_methods:
        method.is_default = promoted_method is not None and method.id == promoted_method.id

    await log_admin_action(
        session,
        admin_id=admin.uid,
        action="billing.remove_payment_method",
        target_user_id=uid,
        details={
            "payment_method_id": payment_method.id,
            "brand": payment_method.brand,
            "last4": payment_method.last4,
            "was_default": deleted_was_default,
            "promoted_payment_method_id": promoted_method.id if promoted_method else None,
        },
        ip_address=request.client.host if request.client else None,
    )
    await session.delete(payment_method)
    await session.commit()
    return {"deleted": True, "payment_method": deleted_payload}


@router.put("/users/{uid}/plan")
async def update_user_plan(
    uid: str,
    payload: PlanUpdate,
    request: Request,
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create or update a user's credit balance plan metadata."""
    await _get_target_user(session, uid)
    balance = await get_or_create_balance(session, uid)
    previous_plan = balance.plan
    previous_allowance = balance.monthly_allowance

    balance.plan = payload.plan
    balance.monthly_allowance = payload.monthly_allowance
    if balance.cycle_start is None or balance.cycle_end is None:
        balance.cycle_start, balance.cycle_end = _get_cycle_bounds(datetime.now(timezone.utc))

    await session.flush()
    await log_admin_action(
        session,
        admin_id=admin.uid,
        action="billing.change_plan",
        target_user_id=uid,
        details={
            "old_plan": previous_plan,
            "new_plan": balance.plan,
            "old_monthly_allowance": previous_allowance,
            "new_monthly_allowance": balance.monthly_allowance,
        },
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    await session.refresh(balance)
    return _serialize_credit_balance(balance)
