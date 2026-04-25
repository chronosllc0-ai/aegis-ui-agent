"""Tests for runtime context accounting and checkpoint creation."""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base
from backend.runtime.context_window import (
    RuntimeContextCheckpoint,
    build_prepared_context,
    estimate_tokens,
    maybe_create_checkpoint,
)
from backend.runtime.persistence import RuntimeRun, RuntimeRunEvent, RuntimeToolCall


def _run(coro):
    return asyncio.run(coro)


async def _make_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_estimate_tokens_is_deterministic() -> None:
    text = "Aegis keeps browser, Slack, GitHub, memory, and chat context together."
    assert estimate_tokens(text) == estimate_tokens(text)
    assert estimate_tokens(text) >= len(text) // 4


def test_build_prepared_context_reports_required_buckets() -> None:
    async def scenario() -> None:
        engine, factory = await _make_db()
        session_id = "agent:main:web:owner-1"
        async with factory() as db:
            db.add_all([
                RuntimeRun(id="run1", owner_uid="owner-1", channel="web", session_id=session_id, status="completed"),
                RuntimeRunEvent(id="ev1", run_id="run1", seq=1, kind="user_message", payload=json.dumps({"text": "Remember budget."})),
                RuntimeRunEvent(id="ev2", run_id="run1", seq=2, kind="final_message", payload=json.dumps({"text": "Saved."})),
                RuntimeToolCall(id="tc1", run_id="run1", event_id="ev1", call_id="call1", owner_uid="owner-1", session_id=session_id, tool_name="github_get_file", arguments=json.dumps({"path": "PLAN.md"}), status="started"),
                RuntimeContextCheckpoint(id="ctx1", owner_uid="owner-1", session_id=session_id, summary="CHECKPOINT: keep the phase plan.", source_event_count=2, token_count=8),
            ])
            await db.commit()

        prepared = await build_prepared_context(
            session_factory=factory,
            session_id=session_id,
            owner_uid="owner-1",
            current_text="Continue phase 8.",
            instructions="You are Aegis.",
            tool_names=["github_get_file", "slack_send_message"],
            model_context_window=2000,
            threshold_pct=90,
        )
        names = {bucket["name"] for bucket in prepared.meter["buckets"]}
        assert {"system_prompt", "active_tools", "checkpoints", "workspace_files", "pinned_memories", "pending_tool_outputs", "chat_history", "current_user_message"}.issubset(names)
        assert prepared.meter["total_tokens"] > 0
        assert "Remember budget" in prepared.prompt
        assert "github_get_file" in prepared.prompt
        assert "CHECKPOINT" in prepared.prompt
        await engine.dispose()

    _run(scenario())


def test_maybe_create_checkpoint_persists_when_threshold_crossed() -> None:
    async def scenario() -> None:
        engine, factory = await _make_db()
        session_id = "agent:main:web:owner-2"
        async with factory() as db:
            db.add_all([
                RuntimeRun(id="run2", owner_uid="owner-2", channel="web", session_id=session_id, status="completed"),
                RuntimeRunEvent(id="ev3", run_id="run2", seq=1, kind="user_message", payload=json.dumps({"text": "important history" * 20})),
            ])
            await db.commit()

        # Tiny window + low threshold so the buckets we plant above
        # (~240 tokens of instructions + current text + history) push
        # the projected percentage past the compaction threshold.
        prepared = await build_prepared_context(
            session_factory=factory,
            session_id=session_id,
            owner_uid="owner-2",
            current_text="current message" * 20,
            instructions="system prompt" * 20,
            tool_names=["read_file", "write_file", "memory_search"],
            model_context_window=300,
            threshold_pct=50,
        )
        assert prepared.meter["should_compact"] is True
        checkpoint = await maybe_create_checkpoint(session_factory=factory, prepared=prepared, owner_uid="owner-2", session_id=session_id)
        assert checkpoint is not None
        assert checkpoint["summary"].startswith("CHECKPOINT:")

        async with factory() as db:
            rows = list((await db.execute(select(RuntimeContextCheckpoint))).scalars())
        assert len(rows) == 1
        assert rows[0].session_id == session_id
        assert rows[0].token_count > 0
        await engine.dispose()

    _run(scenario())
