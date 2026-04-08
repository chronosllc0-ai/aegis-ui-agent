"""Admin skills policy API tests for normalization and persistence behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend import database
from backend.database import PlatformSetting, User
from backend.skills.router import _ADMIN_SKILLS_POLICY_KEY, skills_router


def _init_test_db(tmp_path: Path) -> None:
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'admin_skills_policy.db'}")
    asyncio.run(database.create_tables())


async def _seed_users() -> None:
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


def test_admin_skills_policy_is_normalized_and_persisted(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())

    app = FastAPI()
    app.include_router(skills_router)

    with (
        TestClient(app) as client,
        patch("auth._verify_session", side_effect=_mock_verify_session),
    ):
        client.cookies.set("aegis_session", "admin-1")
        response = client.post(
            "/api/admin/skills/policy",
            json={
                "allow_unreviewed_installs": True,
                "block_high_risk_skills": False,
                "require_approval_before_install": True,
                "default_enabled_skill_ids": ["  skill.alpha  ", "", "   ", "skill.beta"],
            },
        )

    assert response.status_code == 200
    payload = response.json()["policy"]
    assert payload["allow_unreviewed_installs"] is True
    assert payload["block_high_risk_skills"] is False
    assert payload["require_approval_before_install"] is True
    assert payload["default_enabled_skill_ids"] == ["skill.alpha", "skill.beta"]

    async def _assert_db_state() -> None:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            row = await session.execute(select(PlatformSetting).where(PlatformSetting.key == _ADMIN_SKILLS_POLICY_KEY))
            stored = row.scalar_one_or_none()
            assert stored is not None

    asyncio.run(_assert_db_state())


def test_non_admin_cannot_patch_admin_skills_policy(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())

    app = FastAPI()
    app.include_router(skills_router)

    with (
        TestClient(app) as client,
        patch("auth._verify_session", side_effect=_mock_verify_session),
    ):
        client.cookies.set("aegis_session", "user-1")
        response = client.post(
            "/api/admin/skills/policy",
            json={
                "allow_unreviewed_installs": True,
                "block_high_risk_skills": False,
                "require_approval_before_install": True,
                "default_enabled_skill_ids": ["skill.alpha"],
            },
        )

    assert response.status_code == 403
