"""API tests for skill install flows and admin permission gates."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import database
from backend.database import Skill, User, get_session
from backend.skills.service import SkillService
from backend.skills.router import skills_router


def _init_db_sync(tmp_path) -> None:
    async def _run() -> None:
        database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'skills_api.db'}")
        await database.create_tables()
        async for session in get_session():
            session.add_all(
                [
                    User(uid="admin-1", email="admin@example.com", role="admin", status="active"),
                    User(uid="user-1", email="user@example.com", role="user", status="active"),
                ]
            )
            await session.commit()
            break

            
    asyncio.run(_run())


def _seed_approved_skill_sync() -> str:
    async def _run() -> str:
        async for session in get_session():
            skill, submission = await SkillService.submit_skill(
                session,
                slug="hub-installable",
                name="Hub Installable",
                description="desc",
                owner_user_id="admin-1",
                owner_type="admin",
                publish_target="hub",
                metadata_json={},
                skill_markdown="# Safe",
                submitted_by="admin-1",
            )
            await SkillService.run_scans_for_submission(
                session,
                submission_id=submission.id,
                actor_id="admin-1",
                actor_type="admin",
            )
            await SkillService.apply_review_decision(
                session,
                submission_id=submission.id,
                reviewer_admin_id="admin-1",
                decision="approve_hub",
                notes=None,
            )
            await session.commit()
            return skill.id
        raise AssertionError("session unavailable")

    return asyncio.run(_run())


def _mock_verify_session(token: str | None) -> dict[str, str] | None:
    if not token:
        return None
    return {"uid": token}


def test_install_and_enable_flow_appears_in_installed_list(tmp_path) -> None:
    _init_db_sync(tmp_path)
    skill_id = _seed_approved_skill_sync()
    app = FastAPI()
    app.include_router(skills_router)

    with (
        TestClient(app) as client,
        patch("auth._verify_session", side_effect=_mock_verify_session),
        patch("backend.skills.router._verify_session", side_effect=_mock_verify_session),
    ):
        client.cookies.set("aegis_session", "user-1")

        install_response = client.post(f"/api/skills/{skill_id}/install")
        assert install_response.status_code == 200
        assert install_response.json()["enabled"] is True

        installed_response = client.get("/api/skills/installed")
        assert installed_response.status_code == 200
        assert len(installed_response.json()["skills"]) == 1

        disable_response = client.patch(f"/api/skills/{skill_id}/enable", json={"enabled": False})
        assert disable_response.status_code == 200
        assert disable_response.json()["enabled"] is False


def test_admin_review_actions_require_admin_role(tmp_path) -> None:
    _init_db_sync(tmp_path)
    app = FastAPI()
    app.include_router(skills_router)

    with (
        TestClient(app) as client,
        patch("auth._verify_session", side_effect=_mock_verify_session),
        patch("backend.skills.router._verify_session", side_effect=_mock_verify_session),
    ):
        client.cookies.set("aegis_session", "user-1")

        queue_response = client.get("/api/admin/skills/review-queue")
        assert queue_response.status_code == 403
        assert queue_response.json()["detail"] == "Admin access required"


def test_non_admin_submit_forces_hub_publish_target(tmp_path) -> None:
    _init_db_sync(tmp_path)
    app = FastAPI()
    app.include_router(skills_router)

    with (
        TestClient(app) as client,
        patch("auth._verify_session", side_effect=_mock_verify_session),
        patch("backend.skills.router._verify_session", side_effect=_mock_verify_session),
    ):
        client.cookies.set("aegis_session", "user-1")
        response = client.post(
            "/api/skills/submit",
            json={
                "slug": "user-global-attempt",
                "name": "User Global Attempt",
                "description": "desc",
                "publish_target": "global",
                "metadata_json": {},
                "skill_md": "# Safe",
            },
        )
        assert response.status_code == 200

    async def _assert_saved() -> None:
        async for session in get_session():
            row = await session.execute(select(Skill).where(Skill.slug == "user-global-attempt"))
            skill = row.scalar_one()
            assert skill.publish_target == "hub"
            break

    from sqlalchemy import select

    asyncio.run(_assert_saved())
