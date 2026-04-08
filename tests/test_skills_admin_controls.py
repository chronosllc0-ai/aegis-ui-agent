"""Tests for admin skills policy persistence, blocking, and audit pagination."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import database
from backend.database import Skill, SkillVersion, User, get_session
from backend.skills.router import skills_router


def _mock_verify_session(token: str | None) -> dict[str, str] | None:
    return {"uid": token} if token else None


def _init_db_sync(tmp_path) -> str:
    async def _run() -> str:
        database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'skills_admin_controls.db'}")
        await database.create_tables()
        async for session in get_session():
            session.add_all(
                [
                    User(uid="admin-1", email="admin@example.com", role="admin", status="active"),
                    User(uid="user-1", email="user@example.com", role="user", status="active"),
                ]
            )
            skill = Skill(
                slug="blockable-skill",
                name="Blockable Skill",
                description="desc",
                owner_user_id="admin-1",
                owner_type="admin",
                publish_target="hub",
                status="published_hub",
                visibility="public",
                risk_label="clean",
            )
            session.add(skill)
            await session.flush()
            session.add(
                SkillVersion(
                    skill_id=skill.id,
                    version=1,
                    content_sha256="hash-clean",
                    storage_path="inline://test",
                    metadata_json="{}",
                    created_by="admin-1",
                )
            )
            await session.commit()
            return skill.id
        raise AssertionError("session unavailable")

    return asyncio.run(_run())


def test_admin_policy_persists_and_blocklist_prevents_install_and_audit_paginates(tmp_path) -> None:
    skill_id = _init_db_sync(tmp_path)
    app = FastAPI()
    app.include_router(skills_router)

    with (
        TestClient(app) as client,
        patch("auth._verify_session", side_effect=_mock_verify_session),
        patch("backend.skills.router._verify_session", side_effect=_mock_verify_session),
    ):
        client.cookies.set("aegis_session", "admin-1")
        save_policy = client.post(
            "/api/admin/skills/policy",
            json={
                "allow_unreviewed_installs": False,
                "block_high_risk_skills": False,
                "require_approval_before_install": True,
                "default_enabled_skill_ids": [skill_id],
            },
        )
        assert save_policy.status_code == 200

        reload_policy = client.get("/api/admin/skills/policy")
        assert reload_policy.status_code == 200
        payload = reload_policy.json()["policy"]
        assert payload["require_approval_before_install"] is True
        assert skill_id in payload["default_enabled_skill_ids"]

        block_response = client.post(f"/api/admin/skills/{skill_id}/block")
        assert block_response.status_code == 200

        client.cookies.set("aegis_session", "user-1")
        install_response = client.post(f"/api/skills/{skill_id}/install")
        assert install_response.status_code == 400
        assert "blocked" in install_response.json()["detail"].lower()

        client.cookies.set("aegis_session", "admin-1")
        audit_response = client.get("/api/admin/skills/install-audit?page=1&page_size=1")
        assert audit_response.status_code == 200
        audit_payload = audit_response.json()
        assert audit_payload["page"] == 1
        assert audit_payload["page_size"] == 1
        assert audit_payload["total"] >= 1
        assert len(audit_payload["items"]) <= 1
