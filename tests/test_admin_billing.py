"""Regression tests for admin billing routes and validation."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from backend import database
from backend.admin.billing import (
    PaymentMethodCreate,
    PlanUpdate,
    _get_cycle_bounds,
    router as billing_router,
)
from backend.admin.dependencies import get_admin_user
from backend.database import AuditLog, PaymentMethod, User, get_session


def _init_test_db(tmp_path: Path) -> None:
    """Initialize a temporary SQLite database for admin billing tests."""
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'admin_billing.db'}")
    asyncio.run(database.create_tables())


async def _seed_users() -> None:
    """Insert an admin and a regular target user for route tests."""
    async with database._session_factory() as session:  # type: ignore[union-attr]
        session.add_all(
            [
                User(
                    uid="admin-1",
                    email="admin@example.com",
                    role="admin",
                    status="active",
                ),
                User(
                    uid="user-1",
                    email="user@example.com",
                    role="user",
                    status="active",
                ),
            ]
        )
        await session.commit()


def _build_client() -> TestClient:
    """Build a FastAPI test app with admin billing dependency overrides."""
    app = FastAPI()
    app.include_router(billing_router, prefix="/api/admin/billing")

    async def override_admin_user() -> User:
        return User(uid="admin-1", email="admin@example.com", role="admin", status="active")

    async def override_session() -> AsyncGenerator:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            yield session

    app.dependency_overrides[get_admin_user] = override_admin_user
    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


async def _fetch_payment_methods() -> list[PaymentMethod]:
    """Load payment methods for the seeded target user."""
    async with database._session_factory() as session:  # type: ignore[union-attr]
        result = await session.execute(
            select(PaymentMethod)
            .where(PaymentMethod.user_id == "user-1")
            .order_by(PaymentMethod.created_at.asc(), PaymentMethod.id.asc())
        )
        return list(result.scalars().all())


async def _fetch_audit_actions() -> list[str]:
    """Load audit action names for the seeded target user."""
    async with database._session_factory() as session:  # type: ignore[union-attr]
        result = await session.execute(
            select(AuditLog.action)
            .where(AuditLog.target_user_id == "user-1")
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        )
        return [row[0] for row in result.all()]


def test_payment_method_and_plan_models_validate_inputs() -> None:
    """Billing payload models should reject obviously invalid values."""
    PaymentMethodCreate(type="card", brand="visa", last4="4242", exp_month=12, exp_year=2030)
    PlanUpdate(plan="pro", monthly_allowance=1000)

    with pytest.raises(ValidationError):
        PaymentMethodCreate(type="card", brand="visa", last4="42", exp_month=12, exp_year=2030)
    with pytest.raises(ValidationError):
        PaymentMethodCreate(type="card", brand="visa", last4="4242", exp_month=13, exp_year=2030)
    with pytest.raises(ValidationError):
        PlanUpdate(plan="pro", monthly_allowance=-1)


def test_cycle_bounds_handle_january_without_skipping_february() -> None:
    """Billing cycle calculation should advance exactly one month."""
    cycle_start, cycle_end = _get_cycle_bounds(datetime(2026, 1, 31, 14, 0, tzinfo=timezone.utc))

    assert cycle_start.isoformat() == "2026-01-01T00:00:00+00:00"
    assert cycle_end.isoformat() == "2026-01-31T23:59:59+00:00"

    feb_start, feb_end = _get_cycle_bounds(datetime(2026, 2, 10, 9, 30, tzinfo=timezone.utc))
    assert feb_start.isoformat() == "2026-02-01T00:00:00+00:00"
    assert feb_end.isoformat() == "2026-02-28T23:59:59+00:00"


def test_payment_method_routes_keep_a_single_default_and_audit_actions(tmp_path: Path) -> None:
    """Create/default/delete flows should preserve a single default payment method."""
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())
    client = _build_client()

    first_create = client.post(
        "/api/admin/billing/users/user-1/payment-methods",
        json={"type": "card", "brand": "visa", "last4": "1111", "exp_month": 1, "exp_year": 2030},
    )
    assert first_create.status_code == 200
    first_id = first_create.json()["id"]
    assert first_create.json()["is_default"] is True

    second_create = client.post(
        "/api/admin/billing/users/user-1/payment-methods",
        json={"type": "card", "brand": "mastercard", "last4": "2222", "exp_month": 2, "exp_year": 2031},
    )
    assert second_create.status_code == 200
    second_id = second_create.json()["id"]
    assert second_create.json()["is_default"] is False

    set_default = client.put(f"/api/admin/billing/users/user-1/payment-methods/{second_id}/default")
    assert set_default.status_code == 200
    assert set_default.json()["id"] == second_id
    assert set_default.json()["is_default"] is True

    delete_default = client.delete(f"/api/admin/billing/users/user-1/payment-methods/{second_id}")
    assert delete_default.status_code == 200
    assert delete_default.json()["deleted"] is True

    listed = client.get("/api/admin/billing/users/user-1/payment-methods")
    assert listed.status_code == 200
    methods = listed.json()["payment_methods"]
    assert len(methods) == 1
    assert methods[0]["id"] == first_id
    assert methods[0]["is_default"] is True

    payment_methods = asyncio.run(_fetch_payment_methods())
    assert len(payment_methods) == 1
    assert payment_methods[0].id == first_id
    assert payment_methods[0].is_default is True

    actions = asyncio.run(_fetch_audit_actions())
    assert Counter(actions) == Counter(
        [
            "billing.add_payment_method",
            "billing.set_default_payment",
            "billing.remove_payment_method",
        ]
    )
        [
            "billing.add_payment_method",
            "billing.add_payment_method",
            "billing.set_default_payment",
            "billing.remove_payment_method",
        ]
    )
