"""Unit tests for server-authoritative runtime skill resolution."""

from __future__ import annotations

import asyncio
import json

from backend import database
from backend.database import RuntimeSkillInstallation, Skill, SkillToggle, SkillVersion, User, get_session
from backend.skills import runtime as runtime_module
from backend.skills.runtime import resolve_runtime_skills


_RUNNER = asyncio.Runner()


def _run_async(coro: typing.Awaitable[T]) -> T:
    return _RUNNER.run(coro)


def teardown_module(module) -> None:  # noqa: ANN001
    _RUNNER.close()


async def _init_db(tmp_path) -> None:
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'runtime-skills.db'}")
    await database.create_tables()


async def _shutdown_db() -> None:
    """Dispose async DB engine to prevent aiosqlite worker thread teardown races."""
    if database._engine is not None:  # type: ignore[attr-defined]
        await database._engine.dispose()  # type: ignore[attr-defined]
    database._engine = None  # type: ignore[attr-defined]
    database._session_factory = None  # type: ignore[attr-defined]


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
    metadata_json: dict[str, object] | None = None,
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
        metadata_payload = {"skill_md": f"# {skill_id}"}
        if metadata_json:
            metadata_payload.update(metadata_json)
        session.add(
            SkillVersion(
                id=f"v-{skill_id}",
                skill_id=skill_id,
                version=1,
                content_sha256=f"hash-{skill_id}",
                storage_path=f"skills/{skill_id}/v1.md",
                markdown_content=f"# {skill_id}",
                metadata_json=json.dumps(metadata_payload),
                created_by=owner_user_id,
            )
        )
        if installed:
            session.add(RuntimeSkillInstallation(user_id=owner_user_id, skill_id=skill_id))
        session.add(SkillToggle(user_id=owner_user_id, skill_id=skill_id, enabled=enabled))
        await session.commit()
        break


def test_valid_installed_and_enabled_skill_is_resolved(tmp_path) -> None:
    async def _run() -> None:
        try:
            await _init_db(tmp_path)
            await _seed_user()
            await _seed_skill(skill_id="skill-a", status="published_hub", installed=True, enabled=True)

            context = await resolve_runtime_skills("user-1", ["skill-a"])

            assert context.resolved_skill_ids == ["skill-a"]
            assert context.version_hashes["skill-a"] == "hash-skill-a"
            assert context.policy_refs["skill-a"] == "skill_status:published_hub"
        finally:
            await _shutdown_db()

    _run_async(_run())


def test_non_installed_requested_skill_is_ignored(tmp_path) -> None:
    async def _run() -> None:
        try:
            await _init_db(tmp_path)
            await _seed_user()
            await _seed_skill(skill_id="skill-b", status="published_hub", installed=False, enabled=True)

            context = await resolve_runtime_skills("user-1", ["skill-b"])

            assert context.resolved_skill_ids == []
        finally:
            await _shutdown_db()

    _run_async(_run())


def test_disabled_or_revoked_skill_is_not_resolved(tmp_path) -> None:
    async def _run() -> None:
        try:
            await _init_db(tmp_path)
            await _seed_user()
            await _seed_skill(skill_id="skill-c", status="published_hub", installed=True, enabled=False)
            await _seed_skill(skill_id="skill-d", status="draft", installed=True, enabled=True)

            context = await resolve_runtime_skills("user-1", ["skill-c", "skill-d"])

            assert context.resolved_skill_ids == []
        finally:
            await _shutdown_db()

    _run_async(_run())


def test_unauthenticated_user_gets_empty_skill_context() -> None:
    async def _run() -> None:
        context = await resolve_runtime_skills(None, ["skill-z"])

        assert context.resolved_skill_ids == []
        assert context.requested_skill_ids == ["skill-z"]

    _run_async(_run())


def test_runtime_skill_policy_allow_intersection_and_deny_union(tmp_path) -> None:
    async def _run() -> None:
        try:
            await _init_db(tmp_path)
            await _seed_user()
            await _seed_skill(
                skill_id="skill-e",
                status="published_hub",
                installed=True,
                enabled=True,
                metadata_json={"skill_allow_tools": ["read_file", "web_search"], "skill_deny_tools": ["exec_shell"]},
            )
            await _seed_skill(
                skill_id="skill-f",
                status="published_hub",
                installed=True,
                enabled=True,
                metadata_json={"skill_allow_tools": ["read_file", "list_files"], "skill_deny_tools": ["write_file"]},
            )

            context = await resolve_runtime_skills("user-1", ["skill-e", "skill-f"])

            assert context.resolved_skill_ids == ["skill-e", "skill-f"]
            assert context.skill_allow_tools == ["read_file"]
            assert context.skill_deny_tools == ["exec_shell", "write_file"]
        finally:
            await _shutdown_db()

    _run_async(_run())


def test_extract_policy_logs_warning_on_malformed_json(caplog) -> None:
    caplog.set_level("WARNING")
    allow, deny = runtime_module._extract_policy("{bad-json")
    assert allow == set()
    assert deny == set()
    assert "Failed to parse skill metadata_json while extracting runtime policy" in caplog.text
