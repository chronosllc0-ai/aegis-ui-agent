"""Payment processing endpoints — Stripe and Coinbase Commerce."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import CreditBalance, get_session
from backend.credit_rates import PLAN_ALLOWANCES
from config import settings

logger = logging.getLogger(__name__)

payments_router = APIRouter(prefix="/api/payments", tags=["payments"])

# ── Plan → price mapping ──────────────────────────────────────────────────

PLAN_PRICES_USD: dict[str, int] = {
    "pro": 29,
    "team": 79,
    "enterprise": 299,
}

PLAN_NAMES: dict[str, str] = {
    "pro": "Aegis Pro",
    "team": "Aegis Team",
    "enterprise": "Aegis Enterprise",
}

# ── Settings file ─────────────────────────────────────────────────────────

SETTINGS_FILE = Path("/work/repos/aegis-env-fix/payment_settings.json")

DEFAULT_PAYMENT_SETTINGS = {
    "stripe": True,
    "coinbase": True,
}


def _load_payment_settings() -> dict[str, bool]:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            return {**DEFAULT_PAYMENT_SETTINGS, **data}
        except Exception:
            pass
    return dict(DEFAULT_PAYMENT_SETTINGS)


# ── DB helper ─────────────────────────────────────────────────────────────


async def _add_user_credits(user_id: str, credits: int) -> None:
    """Add a one-time credit top-up to a user's balance."""
    async for db in get_session():
        result = await db.execute(
            select(CreditBalance).where(CreditBalance.user_id == user_id)
        )
        balance = result.scalar_one_or_none()
        if balance:
            # Subtract from used (effectively adding credits back)
            balance.credits_used = max(0, balance.credits_used - credits)
        else:
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            balance = CreditBalance(
                user_id=user_id,
                plan="free",
                monthly_allowance=credits,
                credits_used=0,
                cycle_start=now,
                cycle_end=now + timedelta(days=30),
            )
            db.add(balance)
        await db.commit()
        break


async def _update_user_plan(user_id: str, plan: str) -> None:
    """Update a user's plan in the CreditBalance table."""
    async for db in get_session():
        result = await db.execute(
            select(CreditBalance).where(CreditBalance.user_id == user_id)
        )
        balance = result.scalar_one_or_none()
        if balance:
            balance.plan = plan
            balance.monthly_allowance = PLAN_ALLOWANCES.get(plan, 1_000)
        else:
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            balance = CreditBalance(
                user_id=user_id,
                plan=plan,
                monthly_allowance=PLAN_ALLOWANCES.get(plan, 1_000),
                credits_used=0,
                cycle_start=now,
                cycle_end=now + timedelta(days=30),
            )
            db.add(balance)
        await db.commit()
        break


# ── Stripe ────────────────────────────────────────────────────────────────


class StripeCheckoutRequest(BaseModel):
    plan: Literal["pro", "team", "enterprise"]
    success_url: str
    cancel_url: str


@payments_router.post("/stripe/create-checkout")
async def stripe_create_checkout(body: StripeCheckoutRequest) -> dict:
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    price_usd = PLAN_PRICES_USD[body.plan]
    plan_name = PLAN_NAMES[body.plan]

    # Build form-encoded body for Stripe's API
    params = {
        "mode": "subscription",
        "success_url": body.success_url,
        "cancel_url": body.cancel_url,
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][product_data][name]": plan_name,
        "line_items[0][price_data][unit_amount]": str(price_usd * 100),
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][quantity]": "1",
        "metadata[plan]": body.plan,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.stripe.com/v1/checkout/sessions",
            data=params,
            auth=(settings.STRIPE_SECRET_KEY, ""),
            timeout=30,
        )

    if resp.status_code != 200:
        logger.error("Stripe checkout error: %s", resp.text)
        raise HTTPException(status_code=502, detail="Failed to create Stripe checkout session")

    data = resp.json()
    return {"checkout_url": data["url"], "session_id": data["id"]}


@payments_router.post("/stripe/webhook")
async def stripe_webhook(request: Request) -> dict:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if settings.STRIPE_WEBHOOK_SECRET:
        # Verify Stripe signature
        try:
            parts = dict(item.split("=", 1) for item in sig_header.split(",") if "=" in item)
            timestamp = parts.get("t", "")
            signatures = [v for k, v in parts.items() if k == "v1"]
            signed_payload = f"{timestamp}.{payload.decode()}"
            expected = hmac.new(
                settings.STRIPE_WEBHOOK_SECRET.encode(),
                signed_payload.encode(),
                hashlib.sha256,
            ).hexdigest()
            if expected not in signatures:
                raise HTTPException(status_code=400, detail="Invalid Stripe signature")
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Stripe signature verification error: %s", exc)
            raise HTTPException(status_code=400, detail="Signature verification failed") from exc

    try:
        event = json.loads(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    event_type = event.get("type", "")
    data_object = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        metadata = data_object.get("metadata") or {}
        payment_type = metadata.get("type", "plan")
        client_ref = data_object.get("client_reference_id")
        customer_email = data_object.get("customer_email") or (
            data_object.get("customer_details") or {}
        ).get("email")
        user_id = client_ref or metadata.get("user_id") or customer_email

        if payment_type == "credits":
            credits = int(metadata.get("credits", 0))
            if user_id and credits > 0:
                await _add_user_credits(user_id, credits)
                logger.info("Stripe: added %s credits to user %s", credits, user_id)
        else:
            plan = metadata.get("plan", "pro")
            if user_id:
                await _update_user_plan(user_id, plan)
                logger.info("Stripe: upgraded user %s to plan %s", user_id, plan)

    elif event_type == "customer.subscription.deleted":
        customer_id = data_object.get("customer")
        if customer_id:
            logger.info("Stripe: subscription deleted for customer %s, downgrading to free", customer_id)
            # We only have customer_id here; a real implementation would look up the user
            # by customer_id in a mapping table. Log it for now.

    return {"received": True}


# ── Coinbase Commerce ─────────────────────────────────────────────────────


class CoinbaseChargeRequest(BaseModel):
    plan: Literal["pro", "team", "enterprise"]


@payments_router.post("/coinbase/create-charge")
async def coinbase_create_charge(body: CoinbaseChargeRequest) -> dict:
    if not settings.COINBASE_COMMERCE_API_KEY:
        raise HTTPException(status_code=503, detail="Coinbase Commerce is not configured")

    price_usd = PLAN_PRICES_USD[body.plan]
    plan_name = PLAN_NAMES[body.plan]

    charge_payload = {
        "name": plan_name,
        "description": f"Aegis {body.plan.capitalize()} Plan — ${price_usd}/month",
        "pricing_type": "fixed_price",
        "local_price": {
            "amount": str(price_usd),
            "currency": "USD",
        },
        "metadata": {
            "plan": body.plan,
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.commerce.coinbase.com/charges",
            json=charge_payload,
            headers={
                "X-CC-Api-Key": settings.COINBASE_COMMERCE_API_KEY,
                "X-CC-Version": "2018-03-22",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

    if resp.status_code not in (200, 201):
        logger.error("Coinbase Commerce charge error: %s", resp.text)
        raise HTTPException(status_code=502, detail="Failed to create Coinbase charge")

    data = resp.json().get("data", {})
    return {
        "hosted_url": data.get("hosted_url", ""),
        "charge_id": data.get("id", ""),
    }


@payments_router.post("/coinbase/webhook")
async def coinbase_webhook(request: Request) -> dict:
    payload = await request.body()
    sig_header = request.headers.get("x-cc-webhook-signature", "")

    if settings.COINBASE_COMMERCE_WEBHOOK_SECRET:
        expected = hmac.new(
            settings.COINBASE_COMMERCE_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig_header):
            raise HTTPException(status_code=400, detail="Invalid Coinbase webhook signature")

    try:
        event = json.loads(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    event_type = event.get("event", {}).get("type", "")
    data = event.get("event", {}).get("data", {})

    if event_type == "charge:confirmed":
        metadata = data.get("metadata", {})
        payment_type = metadata.get("type", "plan")
        user_id = metadata.get("user_id")
        if payment_type == "credits":
            credits = int(metadata.get("credits", 0))
            if user_id and credits > 0:
                await _add_user_credits(user_id, credits)
                logger.info("Coinbase: added %s credits to user %s", credits, user_id)
        else:
            plan = metadata.get("plan", "pro")
            if user_id:
                await _update_user_plan(user_id, plan)
                logger.info("Coinbase: upgraded user %s to plan %s", user_id, plan)

    return {"received": True}


# ── Config ────────────────────────────────────────────────────────────────


@payments_router.get("/config")
async def get_payments_config() -> dict:
    active_settings = _load_payment_settings()
    active_methods: list[str] = []
    if active_settings.get("stripe") and settings.STRIPE_PUBLISHABLE_KEY:
        active_methods.append("stripe")
    if active_settings.get("coinbase") and settings.COINBASE_COMMERCE_API_KEY:
        active_methods.append("coinbase")
    return {
        "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "active_methods": active_methods,
    }


# ── Credit top-up endpoints ───────────────────────────────────────────────


class StripeCreditsCheckoutRequest(BaseModel):
    credits: int          # total credits to add (including bonus)
    amount_usd: int       # what the user pays
    success_url: str
    cancel_url: str


@payments_router.post("/stripe/create-credits-checkout")
async def stripe_create_credits_checkout(body: StripeCreditsCheckoutRequest, request: Request) -> dict:
    """Create a one-time Stripe checkout session to buy credits."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    # Pull the user id from session cookie if available
    user_id: str | None = None
    try:
        from auth import get_current_user
        user = await get_current_user(request)
        user_id = user.get("uid") if user else None
    except Exception:
        pass

    params = {
        "mode": "payment",
        "success_url": body.success_url,
        "cancel_url": body.cancel_url,
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][product_data][name]": f"Aegis Credits — {body.credits:,} credits",
        "line_items[0][price_data][unit_amount]": str(body.amount_usd * 100),
        "line_items[0][quantity]": "1",
        "metadata[credits]": str(body.credits),
        "metadata[type]": "credits",
    }
    if user_id:
        params["client_reference_id"] = user_id
        params["metadata[user_id]"] = user_id

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.stripe.com/v1/checkout/sessions",
            data=params,
            auth=(settings.STRIPE_SECRET_KEY, ""),
            timeout=30,
        )

    if resp.status_code != 200:
        logger.error("Stripe credits checkout error: %s", resp.text)
        raise HTTPException(status_code=502, detail="Failed to create Stripe checkout session")

    data = resp.json()
    return {"checkout_url": data["url"], "session_id": data["id"]}


class CoinbaseCreditsChargeRequest(BaseModel):
    credits: int
    amount_usd: int


@payments_router.post("/coinbase/create-credits-charge")
async def coinbase_create_credits_charge(body: CoinbaseCreditsChargeRequest, request: Request) -> dict:
    """Create a Coinbase Commerce charge to buy credits with crypto."""
    if not settings.COINBASE_COMMERCE_API_KEY:
        raise HTTPException(status_code=503, detail="Coinbase Commerce is not configured")

    user_id: str | None = None
    try:
        from auth import get_current_user
        user = await get_current_user(request)
        user_id = user.get("uid") if user else None
    except Exception:
        pass

    charge_payload = {
        "name": f"Aegis Credits — {body.credits:,} credits",
        "description": f"Top up {body.credits:,} credits (${body.amount_usd})",
        "pricing_type": "fixed_price",
        "local_price": {"amount": str(body.amount_usd), "currency": "USD"},
        "metadata": {
            "type": "credits",
            "credits": str(body.credits),
            "user_id": user_id or "",
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.commerce.coinbase.com/charges",
            json=charge_payload,
            headers={
                "X-CC-Api-Key": settings.COINBASE_COMMERCE_API_KEY,
                "X-CC-Version": "2018-03-22",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

    if resp.status_code not in (200, 201):
        logger.error("Coinbase credits charge error: %s", resp.text)
        raise HTTPException(status_code=502, detail="Failed to create Coinbase charge")

    data = resp.json().get("data", {})
    return {"hosted_url": data.get("hosted_url", ""), "charge_id": data.get("id", "")}


@payments_router.get("/credit-blocks")
async def get_credit_blocks(request: Request) -> dict:
    """Return a user's credit purchase history (stub — extend with real DB records)."""
    return {"blocks": []}


# ── Invoices ──────────────────────────────────────────────────────────────


@payments_router.get("/invoices")
async def get_invoices(request: Request) -> dict:
    """Return a user's invoice / billing history.

    Pulls from CreditTopUp records (top-ups) and the user's CreditBalance
    for subscription payments.
    """
    user_id: str | None = None
    try:
        from auth import get_current_user
        user = await get_current_user(request)
        user_id = user.get("uid") if user else None
    except Exception:
        pass

    if not user_id:
        return {"invoices": []}

    invoices: list[dict] = []

    async for db in get_session():
        # ── Subscription payment entry ────────────────────────────────────
        result = await db.execute(
            select(CreditBalance).where(CreditBalance.user_id == user_id)
        )
        balance = result.scalar_one_or_none()
        if balance and balance.plan != "free":
            price = PLAN_PRICES_USD.get(balance.plan, 0)
            if price > 0:
                invoices.append({
                    "id": f"sub_{balance.id}",
                    "date": balance.cycle_start.isoformat() if balance.cycle_start else "",
                    "description": f"Aegis {balance.plan.capitalize()} Plan",
                    "amount_usd": price,
                    "status": "paid",
                    "type": "subscription",
                    "payment_method": "card",
                    "invoice_url": None,
                })

        # ── Credit top-up payments ────────────────────────────────────────
        topup_result = await db.execute(
            select(CreditTopUp)
            .where(CreditTopUp.user_id == user_id)
            .order_by(CreditTopUp.created_at.desc())
            .limit(50)
        )
        topups = topup_result.scalars().all()
        for t in topups:
            invoices.append({
                "id": t.id,
                "date": t.created_at.isoformat() if t.created_at else "",
                "description": f"Credit Top-up — {t.credits:,} credits",
                "amount_usd": t.amount_usd,
                "status": "paid",
                "type": "topup",
                "payment_method": "card",
                "invoice_url": None,
            })
        break

    # Sort by date descending
    invoices.sort(key=lambda x: x["date"], reverse=True)
    return {"invoices": invoices}
