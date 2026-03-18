"""Service layer for credit balance management.

All credit operations go through here for atomic updates.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from math import ceil

from sqlalchemy import func as sqlfunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.credit_rates import PLAN_ALLOWANCES, calculate_credits
from backend.database import CreditBalance, CreditTopUp, UsageEvent

logger = logging.getLogger(__name__)


async def get_or_create_balance(session: AsyncSession, user_id: str) -> CreditBalance:
    """Get user's credit balance, creating one if it doesn't exist."""
    result = await session.execute(
        select(CreditBalance).where(CreditBalance.user_id == user_id)
    )
    balance = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if not balance:
        cycle_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (cycle_start + timedelta(days=32)).replace(day=1)
        cycle_end = next_month - timedelta(seconds=1)
        balance = CreditBalance(
            user_id=user_id,
            plan="free",
            monthly_allowance=PLAN_ALLOWANCES["free"],
            credits_used=0,
            overage_credits=0,
            cycle_start=cycle_start,
            cycle_end=cycle_end,
        )
        session.add(balance)
        await session.flush()

    # Auto-reset if billing cycle has expired
    if now > balance.cycle_end:
        cycle_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (cycle_start + timedelta(days=32)).replace(day=1)
        balance.credits_used = 0
        balance.overage_credits = 0
        balance.cycle_start = cycle_start
        balance.cycle_end = next_month - timedelta(seconds=1)
        await session.flush()

    return balance


async def check_credits(session: AsyncSession, user_id: str) -> dict:
    """Check if user has enough credits.  Does *not* deduct."""
    balance = await get_or_create_balance(session, user_id)
    remaining = balance.monthly_allowance - balance.credits_used
    has_credits = remaining > 0 or balance.plan != "free"

    if balance.spending_cap is not None and balance.plan != "free":
        overage_room = balance.spending_cap - balance.overage_credits
        if remaining <= 0 and overage_room <= 0:
            has_credits = False

    return {
        "allowed": has_credits,
        "remaining": max(0, remaining),
        "plan": balance.plan,
        "used": balance.credits_used,
        "allowance": balance.monthly_allowance,
        "overage": balance.overage_credits,
        "percent": round(
            balance.credits_used / balance.monthly_allowance * 100, 1
        )
        if balance.monthly_allowance > 0
        else 100,
        "spending_cap": balance.spending_cap,
        "cycle_end": balance.cycle_end.isoformat() if balance.cycle_end else None,
    }


async def record_usage(
    session: AsyncSession,
    user_id: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    session_id: str | None = None,
) -> dict:
    """Record a usage event and deduct credits atomically.

    Call *after* the provider API call completes with actual token counts.
    Returns a usage summary suitable for the WebSocket ``usage`` message.
    """
    exact, charged, raw_cost = calculate_credits(provider, model, input_tokens, output_tokens)

    event = UsageEvent(
        user_id=user_id,
        session_id=session_id,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        credits_used=exact,
        credits_charged=charged,
        raw_cost_usd=raw_cost,
    )
    session.add(event)

    balance = await get_or_create_balance(session, user_id)
    remaining_in_plan = balance.monthly_allowance - balance.credits_used

    if remaining_in_plan >= charged:
        balance.credits_used += charged
    else:
        plan_portion = max(0, remaining_in_plan)
        overage_portion = charged - plan_portion
        balance.credits_used += plan_portion
        balance.overage_credits += overage_portion

    await session.flush()

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "credits_used": charged,
        "model": model,
        "provider": provider,
        "balance": {
            "used": balance.credits_used + balance.overage_credits,
            "allowance": balance.monthly_allowance,
            "percent": round(
                (balance.credits_used + balance.overage_credits) / balance.monthly_allowance * 100, 1
            ),
            "plan": balance.plan,
        },
    }


async def get_usage_history(
    session: AsyncSession,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    provider: str | None = None,
    model: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    """Get paginated usage history with optional filters."""
    query = select(UsageEvent).where(UsageEvent.user_id == user_id)
    if provider:
        query = query.where(UsageEvent.provider == provider)
    if model:
        query = query.where(UsageEvent.model == model)
    if start_date:
        query = query.where(UsageEvent.created_at >= start_date)
    if end_date:
        query = query.where(UsageEvent.created_at <= end_date)
    query = query.order_by(UsageEvent.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    events = result.scalars().all()

    return {
        "events": [
            {
                "id": e.id,
                "provider": e.provider,
                "model": e.model,
                "input_tokens": e.input_tokens,
                "output_tokens": e.output_tokens,
                "credits_charged": e.credits_charged,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "offset": offset,
        "limit": limit,
    }


async def get_usage_summary(session: AsyncSession, user_id: str) -> dict:
    """Get aggregated usage stats for the dashboard."""
    balance = await get_or_create_balance(session, user_id)

    # Per-provider breakdown
    provider_query = (
        select(
            UsageEvent.provider,
            sqlfunc.sum(UsageEvent.credits_charged).label("total_credits"),
            sqlfunc.count(UsageEvent.id).label("request_count"),
        )
        .where(UsageEvent.user_id == user_id)
        .where(UsageEvent.created_at >= balance.cycle_start)
        .group_by(UsageEvent.provider)
    )
    provider_result = await session.execute(provider_query)
    by_provider = [
        {"provider": r.provider, "credits": int(r.total_credits or 0), "requests": r.request_count}
        for r in provider_result
    ]

    # Per-model breakdown (top 10)
    model_query = (
        select(
            UsageEvent.provider,
            UsageEvent.model,
            sqlfunc.sum(UsageEvent.credits_charged).label("total_credits"),
            sqlfunc.sum(UsageEvent.input_tokens).label("total_input"),
            sqlfunc.sum(UsageEvent.output_tokens).label("total_output"),
            sqlfunc.count(UsageEvent.id).label("request_count"),
        )
        .where(UsageEvent.user_id == user_id)
        .where(UsageEvent.created_at >= balance.cycle_start)
        .group_by(UsageEvent.provider, UsageEvent.model)
        .order_by(sqlfunc.sum(UsageEvent.credits_charged).desc())
        .limit(10)
    )
    model_result = await session.execute(model_query)
    by_model = [
        {
            "provider": r.provider,
            "model": r.model,
            "credits": int(r.total_credits or 0),
            "input_tokens": int(r.total_input or 0),
            "output_tokens": int(r.total_output or 0),
            "requests": r.request_count,
        }
        for r in model_result
    ]

    return {
        "balance": {
            "plan": balance.plan,
            "used": balance.credits_used + balance.overage_credits,
            "allowance": balance.monthly_allowance,
            "overage": balance.overage_credits,
            "percent": round(
                (balance.credits_used + balance.overage_credits) / balance.monthly_allowance * 100, 1
            ),
            "cycle_start": balance.cycle_start.isoformat() if balance.cycle_start else None,
            "cycle_end": balance.cycle_end.isoformat() if balance.cycle_end else None,
            "spending_cap": balance.spending_cap,
        },
        "by_provider": by_provider,
        "by_model": by_model,
    }
