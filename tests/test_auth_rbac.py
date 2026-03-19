"""Auth RBAC regression tests for session payloads and account suspension."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

import auth
from backend import database
from backend.database import User
from config import settings


def _init_test_db(tmp_path: Path) -> None:
    """Initialize a temporary SQLite database for auth tests."""
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'auth_rbac.db'}")
    asyncio.run(database.create_tables())


def test_upsert_existing_user_rejects_suspended_account(tmp_path: Path) -> None:
    """Existing suspended accounts should be rejected before a session is issued."""
    _init_test_db(tmp_path)

    async def _run() -> None:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            session.add(
                User(
                    uid="google:123",
                    provider="google",
                    provider_id="123",
                    email="user@example.com",
                    name="Suspended User",
                    avatar_url=None,
                    role="admin",
                    status="suspended",
                )
            )
            await session.commit()

        async with database._session_factory() as session:  # type: ignore[union-attr]
            with pytest.raises(HTTPException) as exc_info:
                await auth._upsert_user(
                    session,
                    {
                        "uid": "google:123",
                        "provider": "google",
                        "provider_id": "123",
                        "email": "user@example.com",
                        "name": "Suspended User",
                        "avatar_url": None,
                    },
                )
            assert exc_info.value.status_code == 403
            assert exc_info.value.detail == "Account suspended"

    asyncio.run(_run())


def test_upsert_new_user_assigns_admin_role_and_session_payload_exposes_rbac(tmp_path: Path) -> None:
    """New admin-seeded users should include RBAC fields in the returned session payload."""
    _init_test_db(tmp_path)
    original_admin_emails = settings.ADMIN_EMAILS
    original_session_secret = settings.SESSION_SECRET
    settings.ADMIN_EMAILS = "admin@example.com, second@example.com"
    settings.SESSION_SECRET = "test-session-secret"

    async def _run() -> None:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            payload = await auth._upsert_user(
                session,
                {
                    "uid": "password:admin@example.com",
                    "provider": "password",
                    "provider_id": "admin@example.com",
                    "email": "ADMIN@example.com",
                    "name": "Admin User",
                    "avatar_url": None,
                    "password_hash": "pbkdf2_sha256$00$11",
                },
            )

        assert payload["role"] == "admin"
        assert payload["status"] == "active"

        token = auth._sign_session(payload)
        verified = auth._verify_session(token)
        assert verified is not None
        assert verified["uid"] == "password:admin@example.com"
        assert verified["email"] == "ADMIN@example.com"
        assert verified["role"] == "admin"
        assert verified["status"] == "active"

    try:
        asyncio.run(_run())
    finally:
        settings.ADMIN_EMAILS = original_admin_emails
        settings.SESSION_SECRET = original_session_secret


def test_password_login_rejects_non_active_user_before_password_check(tmp_path: Path) -> None:
    """Password login should block suspended accounts before password verification."""
    _init_test_db(tmp_path)
    original_session_secret = settings.SESSION_SECRET
    settings.SESSION_SECRET = "test-session-secret"

    async def _run() -> None:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            session.add(
                User(
                    uid="password:user@example.com",
                    provider="password",
                    provider_id="user@example.com",
                    email="user@example.com",
                    name="Password User",
                    avatar_url=None,
                    role="user",
                    status="suspended",
                    password_hash=auth._hash_password("correct horse battery staple"),
                )
            )
            await session.commit()

        async with database._session_factory() as session:  # type: ignore[union-attr]
            with pytest.raises(HTTPException) as exc_info:
                await auth.password_login(
                    {"email": "user@example.com", "password": "correct horse battery staple"},
                    session=session,
                )
            assert exc_info.value.status_code == 403
            assert exc_info.value.detail == "Account suspended"

    try:
        asyncio.run(_run())
    finally:
        settings.SESSION_SECRET = original_session_secret


def test_password_login_response_includes_role_and_status(tmp_path: Path) -> None:
    """Password login responses should expose RBAC fields while keeping the session valid."""
    _init_test_db(tmp_path)
    original_session_secret = settings.SESSION_SECRET
    settings.SESSION_SECRET = "test-session-secret"

    async def _run() -> None:
        password = "correct horse battery staple"
        async with database._session_factory() as session:  # type: ignore[union-attr]
            session.add(
                User(
                    uid="password:member@example.com",
                    provider="password",
                    provider_id="member@example.com",
                    email="member@example.com",
                    name="Member User",
                    avatar_url=None,
                    role="admin",
                    status="active",
                    password_hash=auth._hash_password(password),
                )
            )
            await session.commit()

        async with database._session_factory() as session:  # type: ignore[union-attr]
            response = await auth.password_login(
                {"email": "member@example.com", "password": password},
                session=session,
            )

        payload = response.body.decode("utf-8")
        assert '"role":"admin"' in payload
        assert '"status":"active"' in payload
        cookie_header = response.headers.get("set-cookie", "")
        token = cookie_header.split("aegis_session=", 1)[1].split(";", 1)[0]
        verified = auth._verify_session(token)
        assert verified is not None
        assert verified["role"] == "admin"
        assert verified["status"] == "active"

    try:
        asyncio.run(_run())
    finally:
        settings.SESSION_SECRET = original_session_secret
