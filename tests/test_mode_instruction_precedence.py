"""Tests for system prompt precedence across global, mode, and runtime instructions."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from backend import database
from backend.admin.platform_settings import GLOBAL_INSTRUCTION_KEY, MODE_INSTRUCTION_KEY_PREFIX
from backend.database import PlatformSetting
import universal_navigator


def _init_test_db(tmp_path: Path) -> None:
    """Initialize a temporary SQLite database for prompt precedence tests."""
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'mode_precedence.db'}")
    asyncio.run(database.create_tables())


def test_prompt_precedence_orders_global_then_mode_then_runtime(tmp_path: Path) -> None:
    """Prompt assembly should preserve authoritative order: global → mode → runtime."""
    _init_test_db(tmp_path)

    async def _run() -> None:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            session.add_all(
                [
                    PlatformSetting(key=GLOBAL_INSTRUCTION_KEY, value="GLOBAL RULE", updated_by="admin-1"),
                    PlatformSetting(
                        key=f"{MODE_INSTRUCTION_KEY_PREFIX}planner",
                        value="PLANNER RULE",
                        updated_by="admin-1",
                    ),
                ]
            )
            await session.commit()

        prompt = await universal_navigator._build_system_prompt(
            session_id="session-precedence",
            settings={"agent_mode": "planner", "system_instruction": "USER RULE"},
            is_subagent=False,
            runtime_skills_section="\n\n### Active Skills (read-only directives)\n[skill:test@v1 source=hub version_id=v1]\nRuntime Guidance:\nSKILL RULE\n",
        )

        global_index = prompt.index("GLOBAL RULE")
        mode_index = prompt.index("PLANNER RULE")
        skill_index = prompt.index("SKILL RULE")
        runtime_index = prompt.index("USER RULE")

        assert global_index < mode_index < skill_index < runtime_index

    asyncio.run(_run())


def test_prompt_uses_default_mode_hint_when_admin_mode_instruction_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mode block should fall back to built-in mode hints when DB has no mode override."""
    _init_test_db(tmp_path)
    monkeypatch.setattr(universal_navigator._app_settings, "AEGIS_GLOBAL_SYSTEM_INSTRUCTION", "")

    async def _run() -> None:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            session.add(PlatformSetting(key=GLOBAL_INSTRUCTION_KEY, value="GLOBAL RULE", updated_by="admin-1"))
            await session.commit()

            stored = await session.execute(
                select(PlatformSetting).where(
                    PlatformSetting.key == f"{MODE_INSTRUCTION_KEY_PREFIX}architect"
                )
            )
            assert stored.scalar_one_or_none() is None

        prompt = await universal_navigator._build_system_prompt(
            session_id="session-default-mode",
            settings={"agent_mode": "architect"},
            is_subagent=False,
            runtime_skills_section="",
        )

        assert "Mode instructions for 'architect'" in prompt
        assert "Provide architecture decisions, tradeoffs, and implementation blueprints" in prompt

    asyncio.run(_run())


def test_prompt_v2_orders_baseline_global_workspace_user_workspace_then_runtime_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v2 prompt mode should merge in the required order with hidden baseline preserved."""
    _init_test_db(tmp_path)
    monkeypatch.setattr(universal_navigator._app_settings, "WORKSPACE_PROMPT_MODE", "v2")

    async def _run() -> None:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            session.add(
                PlatformSetting(
                    key="aegis_workspace_file:AGENTS.MD",
                    value="GLOBAL WS RULE",
                    updated_by="admin-1",
                )
            )
            await session.commit()

        prompt = await universal_navigator._build_system_prompt(
            session_id="session-v2-order",
            settings={
                "user_workspace_overlay_files": {
                    "USER.md": "USER WS RULE",
                },
                "system_instruction": "LEGACY USER INSTRUCTION",
            },
            is_subagent=False,
            runtime_skills_section="\n\nRUNTIME CONTEXT RULE\n",
        )

        baseline_index = prompt.index("Immutable baseline safety policy")
        global_ws_index = prompt.index("GLOBAL WS RULE")
        user_ws_index = prompt.index("USER WS RULE")
        identity_index = prompt.index("You are Aegis, an autonomous AI agent built by Chronos AI.")
        runtime_context_index = prompt.index("RUNTIME CONTEXT RULE")
        custom_index = prompt.index("LEGACY USER INSTRUCTION")
        assert baseline_index < global_ws_index < user_ws_index < identity_index < runtime_context_index < custom_index

    asyncio.run(_run())
