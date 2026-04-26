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


def test_exclude_run_id_filters_current_turn_from_chat_history() -> None:
    """run_started + user_message of the in-flight run must not double-count.

    The dispatch hook records run_started + user_message *before* it
    asks for prepared context. Without the exclude_run_id filter, those
    rows leak into chat_history and the current user message ends up
    counted in two buckets, inflating the meter (Codex P2).
    """

    async def scenario() -> None:
        engine, factory = await _make_db()
        session_id = "agent:main:web:owner-3"
        async with factory() as db:
            db.add_all([
                RuntimeRun(id="run-prev", owner_uid="owner-3", channel="web", session_id=session_id, status="completed"),
                RuntimeRunEvent(id="ev-prev", run_id="run-prev", seq=1, kind="final_message", payload=json.dumps({"text": "earlier turn answer"})),
                RuntimeRun(id="run-now", owner_uid="owner-3", channel="web", session_id=session_id, status="started"),
                RuntimeRunEvent(id="ev-now-start", run_id="run-now", seq=1, kind="run_started", payload=json.dumps({"text": "ZZZUNIQUEZZZ"})),
                RuntimeRunEvent(id="ev-now-msg", run_id="run-now", seq=2, kind="user_message", payload=json.dumps({"text": "ZZZUNIQUEZZZ"})),
            ])
            await db.commit()

        unfiltered = await build_prepared_context(
            session_factory=factory,
            session_id=session_id,
            owner_uid="owner-3",
            current_text="ZZZUNIQUEZZZ",
            instructions="You are Aegis.",
            tool_names=["read_file"],
            model_context_window=10_000,
            threshold_pct=90,
        )
        filtered = await build_prepared_context(
            session_factory=factory,
            session_id=session_id,
            owner_uid="owner-3",
            current_text="ZZZUNIQUEZZZ",
            instructions="You are Aegis.",
            tool_names=["read_file"],
            model_context_window=10_000,
            threshold_pct=90,
            exclude_run_id="run-now",
        )

        def _bucket(meter: dict, name: str) -> dict:
            return next(b for b in meter["buckets"] if b["name"] == name)

        # Filtered version: chat_history holds only the previous turn,
        # not the current ZZZUNIQUEZZZ user message.
        assert "earlier turn answer" in filtered.history_text
        assert "ZZZUNIQUEZZZ" not in filtered.history_text
        # Unfiltered version: ZZZUNIQUEZZZ shows up in history (the bug).
        assert "ZZZUNIQUEZZZ" in unfiltered.history_text
        # Filtering must reduce — never inflate — chat_history tokens.
        assert _bucket(filtered.meter, "chat_history")["tokens"] < _bucket(unfiltered.meter, "chat_history")["tokens"]
        assert filtered.meter["total_tokens"] < unfiltered.meter["total_tokens"]
        await engine.dispose()

    _run(scenario())


def test_compacted_meter_drops_history_and_swaps_checkpoint() -> None:
    """After compaction, the re-emitted meter must reflect the rewritten prompt.

    The dispatch hook rewrites run_input via _checkpoint_prompt() when a
    checkpoint is created, dropping chat_history + pending_tool_outputs
    and replacing the checkpoints bucket with the brand-new summary.
    The post-compaction meter must mirror that shape (Codex P1).
    """

    async def scenario() -> None:
        engine, factory = await _make_db()
        session_id = "agent:main:web:owner-4"
        async with factory() as db:
            db.add_all([
                RuntimeRun(id="run4", owner_uid="owner-4", channel="web", session_id=session_id, status="completed"),
                RuntimeRunEvent(id="ev4", run_id="run4", seq=1, kind="user_message", payload=json.dumps({"text": "long history " * 60})),
                RuntimeToolCall(id="tc4", run_id="run4", event_id="ev4", call_id="call4", owner_uid="owner-4", session_id=session_id, tool_name="github_get_file", arguments="{}", status="started"),
            ])
            await db.commit()

        prepared = await build_prepared_context(
            session_factory=factory,
            session_id=session_id,
            owner_uid="owner-4",
            current_text="next message" * 5,
            instructions="system prompt" * 10,
            tool_names=["read_file", "write_file"],
            model_context_window=400,
            threshold_pct=50,
        )
        assert prepared.meter["should_compact"] is True
        checkpoint_summary = "CHECKPOINT: compressed earlier work."
        post = prepared.compacted_meter(checkpoint_summary=checkpoint_summary)

        def _bucket(meter: dict, name: str) -> dict:
            return next(b for b in meter["buckets"] if b["name"] == name)

        assert _bucket(post, "chat_history")["tokens"] == 0
        assert _bucket(post, "pending_tool_outputs")["tokens"] == 0
        assert _bucket(post, "checkpoints")["tokens"] > 0
        # Post-compaction must report a smaller footprint than pre.
        assert post["total_tokens"] < prepared.meter["total_tokens"]
        # And the buckets that survive (system_prompt, active_tools,
        # current_user_message) keep their token counts.
        for name in ("system_prompt", "active_tools", "current_user_message"):
            assert _bucket(post, name)["tokens"] == _bucket(prepared.meter, name)["tokens"]
        # Owner / session / window / threshold all stay constant.
        assert post["owner_uid"] == prepared.meter["owner_uid"]
        assert post["session_id"] == prepared.meter["session_id"]
        assert post["model_context_window"] == prepared.meter["model_context_window"]
        assert post["compact_threshold_pct"] == prepared.meter["compact_threshold_pct"]
        await engine.dispose()

    _run(scenario())
