"""Unit tests for runtime skill loading policy filters."""

from __future__ import annotations

import asyncio
import json

from backend import database
from backend.database import Skill, SkillReview, SkillScanResult, SkillVersion, User, get_session
from backend.skills.runtime_loader import get_active_runtime_skills


async def _init_db(tmp_path) -> None:
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'runtime_loader.db'}")
    await database.create_tables()


async def _seed_users() -> None:
    async for session in get_session():
        session.add_all(
            [
                User(uid="admin-1", email="admin@example.com", name="Admin", role="admin", status="active"),
                User(uid="user-1", email="user@example.com", name="User", role="user", status="active"),
            ]
        )
        await session.commit()
        break


async def _seed_skill(
    *,
    skill_id: str,
    status: str,
    visibility: str,
    owner_user_id: str,
    version: int,
    metadata: dict[str, object],
) -> str:
    async for session in get_session():
        existing = await session.get(Skill, skill_id)
        if existing is None:
            session.add(
                Skill(
                    id=skill_id,
                    slug=f"{skill_id}-slug",
                    name=f"Skill {skill_id}",
                    description="desc",
                    owner_user_id=owner_user_id,
                    owner_type="admin",
                    status=status,
                    visibility=visibility,
                    risk_label="low",
                )
            )
        else:
            existing.status = status
            existing.visibility = visibility
        version_row = SkillVersion(
            id=f"{skill_id}-v{version}",
            skill_id=skill_id,
            version=version,
            content_sha256=f"sha-{skill_id}-{version}",
            storage_url="inline://test",
            metadata_json=json.dumps(metadata),
            created_by=owner_user_id,
        )
        session.add(version_row)
        await session.commit()
        return version_row.id
    raise AssertionError("session did not yield")


async def _attach_security(version_id: str, *, review_decision: str = "approve_internal") -> None:
    async for session in get_session():
        session.add_all(
            [
                SkillScanResult(skill_version_id=version_id, engine="policy", verdict="pass", score=0.0, raw_json="{}"),
                SkillScanResult(skill_version_id=version_id, engine="virustotal", verdict="pass", score=0.0, raw_json="{}"),
                SkillReview(skill_version_id=version_id, reviewer_admin_id="admin-1", decision=review_decision),
            ]
        )
        await session.commit()
        break


def test_loader_returns_only_approved_and_resolved_latest_versions(tmp_path) -> None:
    async def _run() -> None:
        await _init_db(tmp_path)
        await _seed_users()

        denied_v = await _seed_skill(
            skill_id="draft-skill",
            status="pending_review",
            visibility="global",
            owner_user_id="admin-1",
            version=1,
            metadata={"skill_md": "should not load", "priority": 1},
        )
        await _attach_security(denied_v)

        approved_v1 = await _seed_skill(
            skill_id="approved-skill",
            status="approved_internal",
            visibility="global",
            owner_user_id="admin-1",
            version=1,
            metadata={"skill_md": "old content", "priority": 3},
        )
        await _attach_security(approved_v1)

        approved_v2 = await _seed_skill(
            skill_id="approved-skill",
            status="approved_internal",
            visibility="global",
            owner_user_id="admin-1",
            version=2,
            metadata={"skill_md": "latest content", "priority": 10},
        )
        await _attach_security(approved_v2)

        async for session in get_session():
            runtime = await get_active_runtime_skills(session, user_id="user-1", session_id="session-1")
            assert len(runtime) == 1
            assert runtime[0].skill_id == "approved-skill"
            assert runtime[0].version_id == approved_v2
            assert runtime[0].content == "latest content"
            break

    asyncio.run(_run())


def test_loader_denies_unresolved_review(tmp_path) -> None:
    async def _run() -> None:
        await _init_db(tmp_path)
        await _seed_users()

        unresolved_version = await _seed_skill(
            skill_id="needs-review",
            status="approved_marketplace",
            visibility="hub",
            owner_user_id="admin-1",
            version=1,
            metadata={"skill_md": "danger", "priority": 5},
        )

        async for session in get_session():
            session.add_all(
                [
                    SkillScanResult(skill_version_id=unresolved_version, engine="policy", verdict="pass", score=0.0, raw_json="{}"),
                    SkillScanResult(skill_version_id=unresolved_version, engine="virustotal", verdict="pass", score=0.0, raw_json="{}"),
                ]
            )
            await session.commit()
            break

        async for session in get_session():
            runtime = await get_active_runtime_skills(session, user_id="user-1", session_id="session-1")
            assert runtime == []
            break

    asyncio.run(_run())
