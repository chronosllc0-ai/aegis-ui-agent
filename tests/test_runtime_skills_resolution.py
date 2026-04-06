"""Unit tests for server-authoritative runtime skill resolution."""

from __future__ import annotations

import asyncio
import json

from backend import database
from backend.database import Skill, SkillInstallation, SkillToggle, SkillVersion, User, get_session
from backend.skills.runtime import resolve_runtime_skills


async def _init_db(tmp_path) -> None:
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'runtime-skills.db'}")
    await database.create_tables()


async def _seed_user(uid: str = "user-1") -> None:
    async for session in get_session():
        session.add(User(uid=uid, email=f"{uid}@example.com", name=uid, role="user", status="active"))
        await session.commit()
        break


async def _seed_skill(
    *,
    skill_id: str,
    status: str,
    owner_user_id: str = "user-1",
    installed: bool,
    enabled: bool,
) -> None:
    async for session in get_session():
        skill = Skill(
            id=skill_id,
            slug=f"slug-{skill_id}",
            name=f"Skill {skill_id}",
            status=status,
            visibility="private",
            created_by=owner_user_id,
            owner_user_id=owner_user_id,
            owner_type="user",
            publish_target="hub",
        )
        session.add(skill)
        session.add(
            SkillVersion(
                id=f"v-{skill_id}",
                skill_id=skill_id,
                version=1,
                content_sha256=f"hash-{skill_id}",
                storage_path=f"skills/{skill_id}/v1.md",
                markdown_content=f"# {skill_id}",
                metadata_json=json.dumps({"skill_md": f"# {skill_id}"}),
                created_by=owner_user_id,
            )
        )
        if installed:
            session.add(SkillInstallation(user_id=owner_user_id, skill_id=skill_id))
        session.add(SkillToggle(user_id=owner_user_id, skill_id=skill_id, enabled=enabled))
        await session.commit()
        break


def test_valid_installed_and_enabled_skill_is_resolved(tmp_path) -> None:
    async def _run() -> None:
        await _init_db(tmp_path)
        await _seed_user()
        await _seed_skill(skill_id="skill-a", status="published_hub", installed=True, enabled=True)

        context = await resolve_runtime_skills("user-1", ["skill-a"])

        assert context.resolved_skill_ids == ["skill-a"]
        assert context.version_hashes["skill-a"] == "hash-skill-a"
        assert context.policy_refs["skill-a"] == "skill_status:published_hub"

    asyncio.run(_run())


def test_non_installed_requested_skill_is_ignored(tmp_path) -> None:
    async def _run() -> None:
        await _init_db(tmp_path)
        await _seed_user()
        await _seed_skill(skill_id="skill-b", status="published_hub", installed=False, enabled=True)

        context = await resolve_runtime_skills("user-1", ["skill-b"])

        assert context.resolved_skill_ids == []

    asyncio.run(_run())


def test_disabled_or_revoked_skill_is_not_resolved(tmp_path) -> None:
    async def _run() -> None:
        await _init_db(tmp_path)
        await _seed_user()
        await _seed_skill(skill_id="skill-c", status="published_hub", installed=True, enabled=False)
        await _seed_skill(skill_id="skill-d", status="draft", installed=True, enabled=True)

        context = await resolve_runtime_skills("user-1", ["skill-c", "skill-d"])

        assert context.resolved_skill_ids == []

    asyncio.run(_run())


def test_unauthenticated_user_gets_empty_skill_context() -> None:
    async def _run() -> None:
        context = await resolve_runtime_skills(None, ["skill-z"])

        assert context.resolved_skill_ids == []
        assert context.requested_skill_ids == ["skill-z"]

    asyncio.run(_run())
