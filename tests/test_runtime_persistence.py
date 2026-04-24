"""Phase 7 tests for runtime durability + boot rehydration.

Covers the PLAN.md §Phase 7 merge criteria:

1. Every :class:`~backend.runtime.events.AgentEvent` accepted by
   :class:`SessionSupervisor.enqueue` is persisted to
   ``runtime_inbox_events`` with status ``pending`` *before* the worker
   touches it.
2. A normal dispatch transitions the row through
   ``pending → dispatched → completed`` and fills in ``run_id``.
3. Tool-call checkpoints land in ``runtime_tool_calls`` with their
   native name and arguments, and close out with status ``completed``
   when the Agents SDK emits the matching output item.
4. A "crash" mid-run (simulated by stopping the supervisor with
   ``drain=False`` after we force the inbox row into ``dispatched``) is
   surfaced on rehydration as ``interrupted`` + a
   ``run_interrupted`` fan-out frame, and any in-flight tool-call rows
   are cascaded to ``interrupted``.
5. A row that never reached the worker (``status='pending'``) gets
   re-enqueued on rehydration and the dispatch completes cleanly.

The tests stub the model so they never touch the network and never
require a provider API key. They exercise the real
``backend.runtime.persistence`` schema on in-memory SQLite.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest
from agents import Agent
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base
from backend.runtime import AgentEvent, EventKind, SessionSupervisor
from backend.runtime.agent_loop import DispatchConfig, build_dispatch_hook
from backend.runtime.fanout import FanOutRegistry, RuntimeEvent, Subscriber
from backend.runtime.persistence import (
    RuntimeInboxEvent,
    RuntimeRun,
    RuntimeToolCall,
)
from backend.runtime.rehydration import rehydrate_pending_events
from backend.runtime.supervisor import SupervisorRegistry
from backend.runtime.tools.native import summarize_task


# ---------------------------------------------------------------------------
# Stub model helpers
# ---------------------------------------------------------------------------


class _ToolThenFinalModel(Model):
    """Two-turn stub: turn 1 calls ``summarize_task``, turn 2 finalises."""

    def __init__(self) -> None:
        self.turn = 0

    async def get_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id,
        conversation_id,
        prompt,
    ) -> ModelResponse:
        self.turn += 1
        if self.turn == 1:
            call = ResponseFunctionToolCall(
                id="call_phase7",
                call_id="call_phase7",
                name="summarize_task",
                arguments=json.dumps({"content": "Keep it short.", "max_sentences": 1}),
                type="function_call",
            )
            return ModelResponse(
                output=[call], usage=Usage(), response_id="resp_phase7_1"
            )
        msg = ResponseOutputMessage(
            id="msg_phase7",
            content=[
                ResponseOutputText(
                    type="output_text",
                    text="ok",
                    annotations=[],
                )
            ],
            role="assistant",
            status="completed",
            type="message",
        )
        return ModelResponse(
            output=[msg], usage=Usage(), response_id="resp_phase7_2"
        )

    async def stream_response(self, *args, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError


class _EchoOnlyModel(Model):
    """Single-turn stub: one assistant message, no tool calls."""

    async def get_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id,
        conversation_id,
        prompt,
    ) -> ModelResponse:
        msg = ResponseOutputMessage(
            id="msg_echo",
            content=[
                ResponseOutputText(
                    type="output_text",
                    text="echo",
                    annotations=[],
                )
            ],
            role="assistant",
            status="completed",
            type="message",
        )
        return ModelResponse(output=[msg], usage=Usage(), response_id="resp_echo")

    async def stream_response(self, *args, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Fixtures / scaffolding
# ---------------------------------------------------------------------------


@dataclass
class _TestHarness:
    engine: Any
    session_factory: Any
    fanout: FanOutRegistry


async def _init_harness() -> _TestHarness:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return _TestHarness(
        engine=engine,
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
        fanout=FanOutRegistry(),
    )


def _build_tool_agent(_session, _ctx) -> Agent:
    return Agent(
        name="aegis-phase7",
        instructions="test",
        tools=[summarize_task],
        model=_ToolThenFinalModel(),
    )


def _build_echo_agent(_session, _ctx) -> Agent:
    return Agent(
        name="aegis-phase7-echo",
        instructions="test",
        tools=[],
        model=_EchoOnlyModel(),
    )


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_enqueue_persists_inbox_event_as_pending() -> None:
    """``enqueue`` writes a ``runtime_inbox_events`` row before ``put``."""

    async def scenario() -> None:
        harness = await _init_harness()
        # Supervisor with persistence but a no-op dispatch so we can
        # inspect the pending row before it transitions.
        processed: list[AgentEvent] = []

        async def capture(_sup, event, _session) -> None:
            processed.append(event)

        supervisor = SessionSupervisor(
            "persist-user",
            dispatch=capture,
            persistence_factory=harness.session_factory,
        )
        supervisor.start()
        try:
            await supervisor.enqueue(
                AgentEvent(
                    owner_uid="persist-user",
                    channel="web",
                    kind=EventKind.CHAT_MESSAGE,
                    payload={"text": "hi"},
                    event_id="evt-enqueue",
                )
            )
            for _ in range(200):
                if processed:
                    break
                await asyncio.sleep(0.01)
        finally:
            await supervisor.stop(drain=True)

        async with harness.session_factory() as db:
            row = await db.get(RuntimeInboxEvent, "evt-enqueue")
            assert row is not None, "inbox row must be created on enqueue"
            assert row.owner_uid == "persist-user"
            assert row.channel == "web"
            assert row.kind == "chat_message"
            assert row.session_id == "agent:main:web:persist-user"
            payload = json.loads(row.payload)
            assert payload == {"text": "hi"}

        await harness.engine.dispose()

    _run(scenario())


def test_dispatch_lifecycle_pending_dispatched_completed() -> None:
    """A full dispatch leaves the inbox row at ``status='completed'``."""

    async def scenario() -> None:
        harness = await _init_harness()
        received: list[RuntimeEvent] = []

        async def collector(event: RuntimeEvent) -> None:
            received.append(event)

        hook = build_dispatch_hook(
            DispatchConfig(
                max_turns=4,
                fanout_registry=harness.fanout,
                session_factory=harness.session_factory,
                build_agent_fn=_build_tool_agent,
                connector_loader=lambda _uid: _empty_connectors(),
            )
        )

        supervisor = SessionSupervisor(
            "lifecycle-user",
            dispatch=hook,
            persistence_factory=harness.session_factory,
        )
        supervisor.start()
        try:
            fan = await harness.fanout.get("agent:main:web:lifecycle-user")
            await fan.subscribe(Subscriber(name="t", callback=collector))
            await supervisor.enqueue(
                AgentEvent(
                    owner_uid="lifecycle-user",
                    channel="web",
                    kind=EventKind.CHAT_MESSAGE,
                    payload={"text": "summarize something"},
                    event_id="evt-lifecycle",
                )
            )
            for _ in range(400):
                if any(ev.kind == "run_completed" for ev in received):
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("run never completed")
        finally:
            await supervisor.stop(drain=True)

        async with harness.session_factory() as db:
            row = await db.get(RuntimeInboxEvent, "evt-lifecycle")
            assert row is not None
            assert row.status == "completed"
            assert row.dispatched_at is not None
            assert row.completed_at is not None
            assert row.run_id is not None
            run_row = await db.get(RuntimeRun, row.run_id)
            assert run_row is not None and run_row.status == "completed"

            tool_rows = (
                (await db.execute(select(RuntimeToolCall).where(RuntimeToolCall.run_id == row.run_id)))
                .scalars()
                .all()
            )
            assert len(tool_rows) == 1
            tc = tool_rows[0]
            assert tc.tool_name == "summarize_task"
            assert tc.status == "completed"
            assert tc.call_id == "call_phase7"
            assert tc.arguments is not None and "max_sentences" in tc.arguments
            assert tc.output_preview is not None

        await harness.engine.dispose()

    _run(scenario())


def test_rehydration_marks_dispatched_row_interrupted() -> None:
    """A row in ``dispatched`` is marked ``interrupted`` on rehydration.

    Simulates a crash by planting the row + a live ``runtime_runs`` row
    + an in-flight ``runtime_tool_calls`` row, then running
    :func:`rehydrate_pending_events`. The fan-out should publish a
    ``run_interrupted`` frame for the session.
    """

    async def scenario() -> None:
        harness = await _init_harness()

        # Plant the "crashed" state directly.
        async with harness.session_factory() as db:
            db.add_all(
                [
                    RuntimeRun(
                        id="run-crashed",
                        owner_uid="crash-user",
                        channel="web",
                        session_id="agent:main:web:crash-user",
                        status="running",
                        model="stub",
                    ),
                    RuntimeInboxEvent(
                        event_id="evt-crashed",
                        owner_uid="crash-user",
                        channel="web",
                        session_id="agent:main:web:crash-user",
                        kind="chat_message",
                        priority=10,
                        payload=json.dumps({"text": "was running"}),
                        status="dispatched",
                        created_at=datetime.now(timezone.utc),
                        enqueued_at=datetime.now(timezone.utc),
                        dispatched_at=datetime.now(timezone.utc),
                        run_id="run-crashed",
                    ),
                    RuntimeToolCall(
                        id="tc-crashed",
                        run_id="run-crashed",
                        event_id="evt-crashed",
                        call_id="call_crashed",
                        owner_uid="crash-user",
                        session_id="agent:main:web:crash-user",
                        tool_name="summarize_task",
                        arguments="{}",
                        status="started",
                    ),
                ]
            )
            await db.commit()

        # Subscribe to the session fan-out so we can assert on the
        # ``run_interrupted`` frame.
        received: list[RuntimeEvent] = []

        async def collector(event: RuntimeEvent) -> None:
            received.append(event)

        fan = await harness.fanout.get("agent:main:web:crash-user")
        await fan.subscribe(Subscriber(name="t", callback=collector))

        registry = SupervisorRegistry()
        registry.set_persistence_factory(harness.session_factory)

        summary = await rehydrate_pending_events(
            registry, harness.session_factory, fanout_registry=harness.fanout
        )

        # Let the fan-out deliver the frame.
        for _ in range(50):
            if any(ev.kind == "run_interrupted" for ev in received):
                break
            await asyncio.sleep(0.01)

        assert summary.interrupted == 1
        assert summary.replayed == 0
        assert any(ev.kind == "run_interrupted" for ev in received), [
            ev.kind for ev in received
        ]

        async with harness.session_factory() as db:
            row = await db.get(RuntimeInboxEvent, "evt-crashed")
            assert row is not None and row.status == "interrupted"
            assert row.error and "Supervisor restarted" in row.error
            tc = await db.get(RuntimeToolCall, "tc-crashed")
            assert tc is not None and tc.status == "interrupted"
            run_row = await db.get(RuntimeRun, "run-crashed")
            assert run_row is not None and run_row.status == "interrupted"

        await registry.shutdown()
        await harness.engine.dispose()

    _run(scenario())


def test_rehydration_replays_pending_event() -> None:
    """A ``pending`` row is re-enqueued and processed on rehydration."""

    async def scenario() -> None:
        harness = await _init_harness()

        # Plant a pending row as if the process died between
        # ``record_inbox_event`` and ``inbox.put``.
        async with harness.session_factory() as db:
            db.add(
                RuntimeInboxEvent(
                    event_id="evt-pending",
                    owner_uid="replay-user",
                    channel="web",
                    session_id="agent:main:web:replay-user",
                    kind="chat_message",
                    priority=10,
                    payload=json.dumps({"text": "pick this up"}),
                    status="pending",
                    created_at=datetime.now(timezone.utc),
                    enqueued_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        # Build a registry wired to the echo agent so dispatch completes
        # deterministically without tool calls.
        hook = build_dispatch_hook(
            DispatchConfig(
                max_turns=2,
                fanout_registry=harness.fanout,
                session_factory=harness.session_factory,
                build_agent_fn=_build_echo_agent,
                connector_loader=lambda _uid: _empty_connectors(),
            )
        )
        registry = SupervisorRegistry(dispatch=hook)
        registry.set_persistence_factory(harness.session_factory)

        received: list[RuntimeEvent] = []

        async def collector(event: RuntimeEvent) -> None:
            received.append(event)

        fan = await harness.fanout.get("agent:main:web:replay-user")
        await fan.subscribe(Subscriber(name="t", callback=collector))

        summary = await rehydrate_pending_events(
            registry, harness.session_factory, fanout_registry=harness.fanout
        )
        assert summary.replayed == 1
        assert summary.interrupted == 0

        # Poll the persisted row directly — ``run_completed`` is fanned
        # out *before* ``mark_inbox_completed`` commits, so watching the
        # fan-out would race the persistence write.
        row: RuntimeInboxEvent | None = None
        for _ in range(400):
            async with harness.session_factory() as db:
                row = await db.get(RuntimeInboxEvent, "evt-pending")
            if row is not None and row.status == "completed":
                break
            await asyncio.sleep(0.01)
        assert row is not None
        assert row.status == "completed", row.status

        await registry.shutdown()
        await harness.engine.dispose()

    _run(scenario())


async def _empty_connectors() -> list[Any]:
    return []


def test_rehydration_reconciles_completed_run_with_dispatched_inbox() -> None:
    """Codex PR #342 P2: if the run is already terminal, don't interrupt.

    Crash window: the dispatch hook wrote ``runtime_runs.status =
    'completed'`` but the process died before ``mark_inbox_completed``
    could flush. Before the fix, boot rehydration flipped the inbox
    row to ``interrupted`` and emitted a ``run_interrupted`` frame —
    incorrectly reporting a successful run as crashed. After the fix,
    rehydration drags the inbox row up to match the run's terminal
    status and publishes *no* frame.
    """

    async def scenario() -> None:
        harness = await _init_harness()

        async with harness.session_factory() as db:
            db.add_all(
                [
                    RuntimeRun(
                        id="run-terminal",
                        owner_uid="reconcile-user",
                        channel="web",
                        session_id="agent:main:web:reconcile-user",
                        status="completed",
                        model="stub",
                    ),
                    RuntimeInboxEvent(
                        event_id="evt-terminal",
                        owner_uid="reconcile-user",
                        channel="web",
                        session_id="agent:main:web:reconcile-user",
                        kind="chat_message",
                        priority=10,
                        payload=json.dumps({"text": "already done"}),
                        status="dispatched",
                        created_at=datetime.now(timezone.utc),
                        enqueued_at=datetime.now(timezone.utc),
                        dispatched_at=datetime.now(timezone.utc),
                        run_id="run-terminal",
                    ),
                ]
            )
            await db.commit()

        received: list[RuntimeEvent] = []

        async def collector(event: RuntimeEvent) -> None:
            received.append(event)

        fan = await harness.fanout.get("agent:main:web:reconcile-user")
        await fan.subscribe(Subscriber(name="t", callback=collector))

        registry = SupervisorRegistry()
        registry.set_persistence_factory(harness.session_factory)

        summary = await rehydrate_pending_events(
            registry, harness.session_factory, fanout_registry=harness.fanout
        )

        # Give any would-be fan-out frame a chance to land.
        await asyncio.sleep(0.1)

        assert summary.interrupted == 0, (
            "a run whose run_id is already in a terminal state must not "
            "trigger the interrupted path"
        )
        assert summary.replayed == 0
        assert not any(ev.kind == "run_interrupted" for ev in received), (
            "no run_interrupted frame should be emitted for a run that "
            "actually completed"
        )

        async with harness.session_factory() as db:
            row = await db.get(RuntimeInboxEvent, "evt-terminal")
            assert row is not None
            assert row.status == "completed", row.status
            run_row = await db.get(RuntimeRun, "run-terminal")
            assert run_row is not None and run_row.status == "completed"

        await registry.shutdown()
        await harness.engine.dispose()

    _run(scenario())


def test_finalize_run_and_inbox_is_atomic() -> None:
    """Codex PR #342 P2: run + inbox update share a single commit.

    We call :func:`finalize_run_and_inbox` once and assert both rows
    land in their terminal state inside the same session's commit
    boundary. We can't simulate a mid-function crash in a unit test,
    but we can at least prove the helper does both updates and that
    neither row stays behind.
    """

    async def scenario() -> None:
        harness = await _init_harness()

        # Plant a running run + dispatched inbox row.
        async with harness.session_factory() as db:
            db.add_all(
                [
                    RuntimeRun(
                        id="run-atomic",
                        owner_uid="atomic-user",
                        channel="web",
                        session_id="agent:main:web:atomic-user",
                        status="running",
                        model="stub",
                    ),
                    RuntimeInboxEvent(
                        event_id="evt-atomic",
                        owner_uid="atomic-user",
                        channel="web",
                        session_id="agent:main:web:atomic-user",
                        kind="chat_message",
                        priority=10,
                        payload=json.dumps({"text": "go"}),
                        status="dispatched",
                        created_at=datetime.now(timezone.utc),
                        enqueued_at=datetime.now(timezone.utc),
                        dispatched_at=datetime.now(timezone.utc),
                        run_id="run-atomic",
                    ),
                ]
            )
            await db.commit()

        from backend.runtime.persistence import finalize_run_and_inbox

        async with harness.session_factory() as db:
            await finalize_run_and_inbox(
                db,
                run_id="run-atomic",
                event_id="evt-atomic",
                run_status="completed",
            )

        async with harness.session_factory() as db:
            run_row = await db.get(RuntimeRun, "run-atomic")
            inbox_row = await db.get(RuntimeInboxEvent, "evt-atomic")
            assert run_row is not None
            assert inbox_row is not None
            assert run_row.status == "completed"
            assert run_row.ended_at is not None
            assert inbox_row.status == "completed"
            assert inbox_row.completed_at is not None

        await harness.engine.dispose()

    _run(scenario())
