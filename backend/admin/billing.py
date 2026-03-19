"""Admin billing management routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.audit_service import log_admin_action
from backend.admin.dependencies import get_admin_user
from backend.credit_service import get_or_create_balance
from backend.database import CreditBalance, PaymentMethod, User, get_session

router = APIRouter(dependencies=[Depends(get_admin_user)])


class PaymentMethodCreate(BaseModel):
    """Payload for creating a payment method."""

    type: str
    brand: str
    last4: str
    exp_month: int
    exp_year: int


class PlanUpdate(BaseModel):
    """Payload for updating a user's billing plan."""

    plan: str
    monthly_allowance: int


async def _get_target_user(session: AsyncSession, uid: str) -> User:
    """Load the target user or raise a 404."""
    user = await session.get(User, uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _get_user_payment_method(
    session: AsyncSession,
    *,
    uid: str,
    pm_id: str,
) -> PaymentMethod:
    """Load a payment method for the target user or raise a 404."""
    payment_method = await session.get(PaymentMethod, pm_id)
    if not payment_method or payment_method.user_id != uid:
        raise HTTPException(status_code=404, detail="Payment method not found")
    return payment_method


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

    existing_default = await session.scalar(
        select(PaymentMethod.id).where(
            PaymentMethod.user_id == uid,
            PaymentMethod.is_default.is_(True),
        )
    )
    is_default = existing_default is None

    payment_method = PaymentMethod(
        user_id=uid,
        type=payload.type,
        brand=payload.brand,
        last4=payload.last4,
        exp_month=payload.exp_month,
        exp_year=payload.exp_year,
        is_default=is_default,
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
    payment_method = await _get_user_payment_method(session, uid=uid, pm_id=pm_id)

    await session.execute(
        update(PaymentMethod)
        .where(PaymentMethod.user_id == uid, PaymentMethod.id != payment_method.id)
        .values(is_default=False)
    )
    payment_method.is_default = True
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
    payment_method = await _get_user_payment_method(session, uid=uid, pm_id=pm_id)
    deleted_payload = _serialize_payment_method(payment_method)
    deleted_was_default = bool(payment_method.is_default)

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
        },
        ip_address=request.client.host if request.client else None,
    )
    await session.delete(payment_method)

    if deleted_was_default:
        next_method = await session.scalar(
            select(PaymentMethod)
            .where(PaymentMethod.user_id == uid, PaymentMethod.id != pm_id)
            .order_by(PaymentMethod.created_at.asc())
            .limit(1)
        )
        if next_method:
            next_method.is_default = True

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
    now = datetime.now(timezone.utc)
    if balance.cycle_start is None or balance.cycle_end is None:
        cycle_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (cycle_start + timedelta(days=32)).replace(day=1)
        balance.cycle_start = cycle_start
        balance.cycle_end = next_month - timedelta(seconds=1)

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
