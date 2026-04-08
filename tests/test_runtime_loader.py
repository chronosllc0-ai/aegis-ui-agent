"""Unit tests for runtime skill install/use gating."""

from __future__ import annotations

import asyncio
import json

from backend import database
from backend.database import Skill, SkillInstall, SkillReview, SkillScanResult, SkillVersion, User, get_session
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


async def _seed_skill(*, skill_id: str, status: str, publish_target: str, owner_user_id: str, version: int, metadata: dict[str, object]) -> str:
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
                    publish_target=publish_target,
                    status=status,
                    risk_label="low",
                )
            )
        else:
            existing.status = status
            existing.publish_target = publish_target
        version_row = SkillVersion(
            id=f"{skill_id}-v{version}",
            skill_id=skill_id,
            version=version,
            content_sha256=f"sha-{skill_id}-{version}",
            storage_path="inline://test",
            metadata_json=json.dumps(metadata),
            created_by=owner_user_id,
        )
        session.add(version_row)
        await session.commit()
        return version_row.id
    raise AssertionError("session did not yield")


async def _attach_security(version_id: str, *, review_decision: str = "approve_global") -> None:
    async for session in get_session():
        session.add_all(
            [
                SkillScanResult(skill_version_id=version_id, engine="policy", verdict="pass", risk_label="low", raw_json="{}"),
                SkillScanResult(skill_version_id=version_id, engine="virustotal", verdict="pass", risk_label="low", raw_json="{}"),
                SkillReview(skill_version_id=version_id, reviewer_admin_id="admin-1", decision=review_decision),
            ]
        )
        await session.commit()
        break


async def _install(user_id: str, skill_id: str, version_id: str, *, enabled: bool = True) -> None:
    async for session in get_session():
        session.add(
            SkillInstall(
                user_id=user_id,
                skill_id=skill_id,
                skill_version_id=version_id,
                enabled=enabled,
            )
        )
        await session.commit()
        break


def test_loader_returns_only_installed_enabled_and_approved_skills(tmp_path) -> None:
    async def _run() -> None:
        await _init_db(tmp_path)
        await _seed_users()

        approved_v = await _seed_skill(
            skill_id="approved-skill",
            status="published_global",
            publish_target="global",
            owner_user_id="admin-1",
            version=1,
            metadata={"skill_md": "latest content"},
        )
        await _attach_security(approved_v)
        await _install("user-1", "approved-skill", approved_v, enabled=True)

        disabled_v = await _seed_skill(
            skill_id="disabled-skill",
            status="published_hub",
            publish_target="hub",
            owner_user_id="admin-1",
            version=1,
            metadata={"skill_md": "disabled content"},
        )
        await _attach_security(disabled_v, review_decision="approve_hub")
        await _install("user-1", "disabled-skill", disabled_v, enabled=False)

        async for session in get_session():
            runtime = await get_active_runtime_skills(session, user_id="user-1", session_id="session-1")
            assert len(runtime) == 1
            assert runtime[0].skill_id == "approved-skill"
            assert runtime[0].version_id == approved_v
            assert runtime[0].content == "latest content"
            break

    asyncio.run(_run())


def test_loader_blocks_unapproved_skill_even_if_installed(tmp_path) -> None:
    async def _run() -> None:
        await _init_db(tmp_path)
        await _seed_users()

        pending_v = await _seed_skill(
            skill_id="pending-skill",
            status="review",
            publish_target="hub",
            owner_user_id="admin-1",
            version=1,
            metadata={"skill_md": "should not load"},
        )
        await _attach_security(pending_v, review_decision="approve_hub")
        await _install("user-1", "pending-skill", pending_v, enabled=True)

        async for session in get_session():
            runtime = await get_active_runtime_skills(session, user_id="user-1", session_id="session-1")
            assert runtime == []
            break

    asyncio.run(_run())
