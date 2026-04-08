from __future__ import annotations

import asyncio

from backend import database
from backend.database import Skill, SkillVersion, User, get_session
from backend.skills.policy_store import set_skills_policy
from backend.skills.service import SkillService
from config import settings


async def _init_db(tmp_path) -> None:
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'skills_install_policy.db'}")
    await database.create_tables()


async def _seed_user() -> None:
    async for session in get_session():
        session.add(User(uid="user-1", email="user@example.com", role="user", status="active"))
        await session.commit()
        break


async def _create_skill(*, risk_label: str) -> str:
    async for session in get_session():
        skill = Skill(
            slug=f"skill-{risk_label}",
            name=f"Skill {risk_label}",
            description="desc",
            owner_user_id="user-1",
            owner_type="user",
            publish_target="hub",
            status="published_hub",
            visibility="public",
            risk_label=risk_label,
        )
        session.add(skill)
        await session.flush()
        session.add(
            SkillVersion(
                skill_id=skill.id,
                version=1,
                content_sha256=f"hash-{risk_label}",
                storage_path="inline://test",
                metadata_json="{}",
                created_by="user-1",
            )
        )
        await session.commit()
        return skill.id
    raise AssertionError('unable to create skill')


def test_install_policy_blocks_malicious_and_suspicious(tmp_path) -> None:
    async def _run() -> None:
        await _init_db(tmp_path)
        await _seed_user()
        malicious_id = await _create_skill(risk_label="malicious")
        suspicious_id = await _create_skill(risk_label="suspicious")

        async for session in get_session():
            await set_skills_policy(
                session,
                policy={
                    "allow_unreviewed_installs": False,
                    "block_high_risk_skills": True,
                    "require_approval_before_install": False,
                    "default_enabled_skill_ids": [],
                },
                admin_uid="user-1",
            )
            await session.commit()
            try:
                await SkillService.install_skill(session, user_id="user-1", skill_id=malicious_id)
            except ValueError as exc:
                assert "malicious" in str(exc)
            else:
                raise AssertionError("malicious install should be blocked")

            try:
                await SkillService.install_skill(session, user_id="user-1", skill_id=suspicious_id)
            except ValueError as exc:
                assert "org policy" in str(exc)
            else:
                raise AssertionError("suspicious install should be blocked")
            break

    asyncio.run(_run())


def test_install_policy_respects_pending_fallback_block(tmp_path) -> None:
    async def _run() -> None:
        await _init_db(tmp_path)
        await _seed_user()
        pending_id = await _create_skill(risk_label="scan_pending")

        old = settings.VIRUSTOTAL_FALLBACK_POLICY
        settings.VIRUSTOTAL_FALLBACK_POLICY = "block"
        try:
            async for session in get_session():
                try:
                    await SkillService.install_skill(session, user_id="user-1", skill_id=pending_id)
                except ValueError as exc:
                    assert "scan_pending" in str(exc)
                else:
                    raise AssertionError("scan_pending should be blocked when fallback=block")
                break
        finally:
            settings.VIRUSTOTAL_FALLBACK_POLICY = old

    asyncio.run(_run())
