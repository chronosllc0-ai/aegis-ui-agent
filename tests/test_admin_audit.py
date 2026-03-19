"""Regression tests for admin audit listing routes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import database
from backend.admin.audit import router as audit_router
from backend.admin.dependencies import get_admin_user
from backend.database import AuditLog, User, get_session


def _init_test_db(tmp_path: Path) -> None:
    """Initialize a temporary SQLite database for admin audit tests."""
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'admin_audit.db'}")
    asyncio.run(database.create_tables())


async def _seed_audit_logs() -> None:
    """Insert an admin, user, and audit rows for listing tests."""
    async with database._session_factory() as session:  # type: ignore[union-attr]
        session.add_all(
            [
                User(uid="admin-1", email="admin@example.com", role="admin", status="active"),
                User(uid="admin-2", email="other-admin@example.com", role="admin", status="active"),
                User(uid="user-1", email="user1@example.com", role="user", status="active"),
                User(uid="user-2", email="user2@example.com", role="user", status="active"),
            ]
        )
        session.add_all(
            [
                AuditLog(
                    id="audit-1",
                    admin_id="admin-1",
                    action="billing.add_payment_method",
                    target_user_id="user-1",
                    details_json='{"ok": true}',
                    ip_address="10.0.0.1",
                    created_at=datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc),
                ),
                AuditLog(
                    id="audit-2",
                    admin_id="admin-1",
                    action="users.suspend",
                    target_user_id="user-2",
                    details_json='{bad json',
                    ip_address="10.0.0.2",
                    created_at=datetime(2026, 3, 18, 15, 30, tzinfo=timezone.utc),
                ),
                AuditLog(
                    id="audit-3",
                    admin_id="admin-2",
                    action="users.restore",
                    target_user_id="user-1",
                    details_json='["restored"]',
                    ip_address="10.0.0.3",
                    created_at=datetime(2026, 3, 19, 9, 45, tzinfo=timezone.utc),
                ),
            ]
        )
        await session.commit()


def _build_client() -> TestClient:
    """Build a FastAPI test app with admin audit dependency overrides."""
    app = FastAPI()
    app.include_router(audit_router, prefix="/api/admin/audit")

    async def override_admin_user() -> User:
        return User(uid="admin-1", email="admin@example.com", role="admin", status="active")

    async def override_session() -> AsyncGenerator:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            yield session

    app.dependency_overrides[get_admin_user] = override_admin_user
    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def test_list_audit_entries_filters_and_decodes_defensively(tmp_path: Path) -> None:
    """Audit endpoint should filter dynamically and tolerate malformed details JSON."""
    _init_test_db(tmp_path)
    asyncio.run(_seed_audit_logs())
    client = _build_client()

    response = client.get(
        "/api/admin/audit/",
        params={
            "admin_id": "admin-1",
            "date_from": "2026-03-18T00:00:00Z",
            "date_to": "2026-03-19T00:00:00+00:00",
            "limit": 10,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [entry["id"] for entry in payload["entries"]] == ["audit-2"]
    assert payload["entries"][0]["details"] == "{bad json"
    assert payload["entries"][0]["created_at"] == "2026-03-18T15:30:00"


def test_list_audit_entries_supports_action_target_and_pagination(tmp_path: Path) -> None:
    """Audit endpoint should apply optional filters and pagination consistently."""
    _init_test_db(tmp_path)
    asyncio.run(_seed_audit_logs())
    client = _build_client()

    response = client.get(
        "/api/admin/audit/",
        params={"action": "users.restore", "target_user_id": "user-1", "limit": 1, "offset": 0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["id"] == "audit-3"
    assert payload["entries"][0]["details"] == ["restored"]


def test_list_audit_entries_rejects_invalid_iso_timestamps(tmp_path: Path) -> None:
    """Audit endpoint should return HTTP 400 when timestamp filters are invalid."""
    _init_test_db(tmp_path)
    asyncio.run(_seed_audit_logs())
    client = _build_client()

    response = client.get("/api/admin/audit/", params={"date_from": "not-a-timestamp"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid date_from timestamp"
