"""API tests for admin platform settings authorization and mode-instruction persistence."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend import database
from backend.admin.platform_settings import GLOBAL_INSTRUCTION_KEY, MODE_INSTRUCTION_KEY_PREFIX, router
from backend.database import PlatformSetting, User


def _init_test_db(tmp_path: Path) -> None:
    """Initialize a temporary SQLite database for platform settings route tests."""
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'admin_platform_settings.db'}")
    asyncio.run(database.create_tables())


async def _seed_users() -> None:
    """Insert one admin and one non-admin user."""
    async with database._session_factory() as session:  # type: ignore[union-attr]
        session.add_all(
            [
                User(uid="admin-1", email="admin@example.com", role="admin", status="active"),
                User(uid="user-1", email="user@example.com", role="user", status="active"),
            ]
        )
        await session.commit()


def _mock_verify_session(token: str | None) -> dict[str, str] | None:
    if not token:
        return None
    return {"uid": token}


def test_platform_settings_patch_requires_admin_role(tmp_path: Path) -> None:
    """Non-admin users should be denied when attempting to mutate platform settings."""
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())
    app = FastAPI()
    app.include_router(router, prefix="/api/admin")

    with (
        TestClient(app) as client,
        patch("auth._verify_session", side_effect=_mock_verify_session),
    ):
        client.cookies.set("aegis_session", "user-1")
        response = client.patch(
            "/api/admin/platform-settings",
            json={
                "global_system_instruction": "global",
                "mode_system_instructions": {"orchestrator": "mode"},
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_admin_can_patch_global_and_mode_instructions(tmp_path: Path) -> None:
    """Admin writes should persist both global and mode instruction definitions."""
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())
    app = FastAPI()
    app.include_router(router, prefix="/api/admin")

    with (
        TestClient(app) as client,
        patch("auth._verify_session", side_effect=_mock_verify_session),
    ):
        client.cookies.set("aegis_session", "admin-1")
        response = client.patch(
            "/api/admin/platform-settings",
            json={
                "global_system_instruction": "GLOBAL POLICY",
                "mode_system_instructions": {
                    "orchestrator": "ORCHESTRATOR POLICY",
                    "planner": "PLANNER POLICY",
                    "architect": "",
                    "deep_research": "",
                    "code": "",
                },
            },
        )
        assert response.status_code == 200

    async def _assert_saved() -> None:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            global_row = await session.execute(
                select(PlatformSetting).where(PlatformSetting.key == GLOBAL_INSTRUCTION_KEY)
            )
            orchestrator_row = await session.execute(
                select(PlatformSetting).where(
                    PlatformSetting.key == f"{MODE_INSTRUCTION_KEY_PREFIX}orchestrator"
                )
            )
            planner_row = await session.execute(
                select(PlatformSetting).where(PlatformSetting.key == f"{MODE_INSTRUCTION_KEY_PREFIX}planner")
            )

            assert global_row.scalar_one().value == "GLOBAL POLICY"
            assert orchestrator_row.scalar_one().value == "ORCHESTRATOR POLICY"
            assert planner_row.scalar_one().value == "PLANNER POLICY"

    asyncio.run(_assert_saved())
