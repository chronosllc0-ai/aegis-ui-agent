"""State-machine tests for Skill Hub workflow transitions."""

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
        database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'skills_hub_states.db'}")
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


def _mock_verify_session(token: str | None) -> dict[str, str] | None:
    if not token:
        return None
    return {"uid": token}


def test_legal_and_illegal_transitions_are_enforced(tmp_path) -> None:
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
            json={
                "skill_id": "skill-1",
                "skill_slug": "skill-1",
                "title": "Skill One",
                "description": "desc",
                "submit_now": True,
            },
        )
        assert created.status_code == 200
        submission_id = created.json()["submission"]["id"]

        illegal = client.post(
            f"/api/skills/hub/submissions/{submission_id}/transition",
            json={"next_state": "approved"},
        )
        assert illegal.status_code == 400
        assert "Illegal transition" in illegal.json()["detail"]

        client.cookies.set("aegis_session", "admin-1")
        under_review = client.post(
            f"/api/skills/hub/submissions/{submission_id}/transition",
            json={"next_state": "under_review"},
        )
        assert under_review.status_code == 200

        approved = client.post(
            f"/api/skills/hub/submissions/{submission_id}/transition",
            json={"next_state": "approved", "notes": "Looks good"},
        )
        assert approved.status_code == 200

        published = client.post(
            f"/api/skills/hub/submissions/{submission_id}/transition",
            json={"next_state": "published"},
        )
        assert published.status_code == 200

        state = published.json()["submission"]["current_state"]
        assert state == "published"


def test_rejected_is_terminal_and_resubmit_requires_new_revision(tmp_path) -> None:
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
            json={"skill_slug": "skill-2", "title": "Skill Two", "submit_now": True},
        )
        submission_id = created.json()["submission"]["id"]

        client.cookies.set("aegis_session", "admin-1")
        client.post(f"/api/skills/hub/submissions/{submission_id}/transition", json={"next_state": "under_review"})
        rejected = client.post(
            f"/api/skills/hub/submissions/{submission_id}/transition",
            json={"next_state": "rejected", "notes": "Unsafe"},
        )
        assert rejected.status_code == 200

        blocked = client.post(
            f"/api/skills/hub/submissions/{submission_id}/transition",
            json={"next_state": "submitted"},
        )
        assert blocked.status_code == 400

        client.cookies.set("aegis_session", "user-1")
        resubmitted = client.post(
            "/api/skills/hub/submissions",
            json={
                "skill_slug": "skill-2",
                "title": "Skill Two v2",
                "previous_submission_id": submission_id,
                "submit_now": True,
            },
        )
        assert resubmitted.status_code == 200
        assert resubmitted.json()["submission"]["revision"] == 2
