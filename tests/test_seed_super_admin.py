"""Regression tests for the super-admin seed script."""

from __future__ import annotations

import asyncio
from pathlib import Path

import auth
from backend import database
from backend.database import User
from config import settings
from scripts.seed_super_admin import seed_super_admin


def test_seed_super_admin_creates_and_updates_password_user(tmp_path: Path) -> None:
    """Seeding should create a superadmin account and update it idempotently."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'seed_super_admin.db'}"
    original_session_secret = settings.SESSION_SECRET
    settings.SESSION_SECRET = "test-session-secret"

    async def _run() -> None:
        created = await seed_super_admin(
            email="root@example.com",
            password="Password123!",
            name="Root Admin",
            database_url=db_url,
        )
        assert created["created"] is True
        assert created["uid"] == "password:root@example.com"
        assert created["role"] == "superadmin"

        updated = await seed_super_admin(
            email="root@example.com",
            password="NewPassword123!",
            name="Updated Root Admin",
            database_url=db_url,
        )
        assert updated["created"] is False
        assert updated["role"] == "superadmin"

        async with database._session_factory() as session:  # type: ignore[union-attr]
            user = await session.get(User, "password:root@example.com")

        assert user is not None
        assert user.role == "superadmin"
        assert user.status == "active"
        assert user.name == "Updated Root Admin"
        assert auth._verify_password("NewPassword123!", user.password_hash) is True

    try:
        asyncio.run(_run())
    finally:
        settings.SESSION_SECRET = original_session_secret
