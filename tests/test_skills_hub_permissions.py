"""Permission checks for Skill Hub transition and review queue endpoints."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import database
from backend.database import User, get_session
from backend.skills_hub.router import skills_hub_router


def _init_db_sync(tmp_path) -> None:
    async def _run() -> None:
        database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'skills_hub_permissions.db'}")
        await database.create_tables()
        async for session in get_session():
            session.add_all(
                [
                    User(uid="admin-1", email="admin@example.com", role="admin", status="active"),
                    User(uid="user-1", email="user@example.com", role="user", status="active"),
                    User(uid="user-2", email="user2@example.com", role="user", status="active"),
                ]
            )
            await session.commit()
            break

    asyncio.run(_run())


def _mock_verify_session(token: str | None) -> dict[str, str] | None:
    if not token:
        return None
    return {"uid": token}


def test_only_admin_can_access_review_queue(tmp_path) -> None:
    _init_db_sync(tmp_path)
    app = FastAPI()
    app.include_router(skills_hub_router)

    with (
        TestClient(app) as client,
        patch("auth._verify_session", side_effect=_mock_verify_session),
        patch("backend.skills_hub.router._verify_session", side_effect=_mock_verify_session),
    ):
        client.cookies.set("aegis_session", "user-1")
        forbidden = client.get("/api/skills/hub/review-queue")
        assert forbidden.status_code == 403

        client.cookies.set("aegis_session", "admin-1")
        ok = client.get("/api/skills/hub/review-queue")
        assert ok.status_code == 200


def test_user_cannot_transition_other_user_submission_or_admin_only_steps(tmp_path) -> None:
    _init_db_sync(tmp_path)
    app = FastAPI()
    app.include_router(skills_hub_router)

    with (
        TestClient(app) as client,
        patch("auth._verify_session", side_effect=_mock_verify_session),
        patch("backend.skills_hub.router._verify_session", side_effect=_mock_verify_session),
    ):
        client.cookies.set("aegis_session", "user-1")
        created = client.post(
            "/api/skills/hub/submissions",
            json={"skill_slug": "perm-skill", "title": "Permissions", "submit_now": True},
        )
        submission_id = created.json()["submission"]["id"]

        client.cookies.set("aegis_session", "user-2")
        other_user_forbidden = client.get(f"/api/skills/hub/submissions/{submission_id}")
        assert other_user_forbidden.status_code == 403

        transition_forbidden = client.post(
            f"/api/skills/hub/submissions/{submission_id}/transition",
            json={"next_state": "under_review"},
        )
        assert transition_forbidden.status_code == 403
