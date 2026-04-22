"""Phase 1 scaffold tests for the always-on runtime.

These tests lock in the scaffolding contract so Phase 2 (agent loop),
Phase 6 (heartbeat rework), and Phase 7 (context meter) can rely on it:

- Priority ordering: user chat beats heartbeat beats background.
- Per-user isolation: supervisors do not share queues.
- Channel-session materialization: every channel has its own session
  under the shared supervisor.
- Shutdown: ``stop()`` drains cleanly.
- Registry: ``SupervisorRegistry.get(uid)`` is idempotent.

We do not depend on pytest-asyncio to stay consistent with the existing
test suite conventions (see tests/test_reasoning_commands.py).
"""

from __future__ import annotations

import asyncio

import pytest

from backend.runtime import (
    AgentEvent,
    ChannelSession,
    EventKind,
    SessionSupervisor,
    SupervisorRegistry,
)
from backend.runtime.events import EventPriority
from backend.runtime.session import ChannelSessionKey


def _run(coro):
    return asyncio.run(coro)


def test_supervisor_materializes_channel_session_on_demand() -> None:
    async def scenario() -> None:
        supervisor = SessionSupervisor("user-a")
        supervisor.start()
        try:
            await supervisor.enqueue(
                AgentEvent(owner_uid="user-a", channel="slack", kind=EventKind.CHAT_MESSAGE)
            )
            # Give the worker a tick so it drains.
            for _ in range(50):
                if supervisor.stats.processed >= 1:
                    break
                await asyncio.sleep(0.01)
        finally:
            await supervisor.stop()
        sessions = supervisor.sessions()
        assert len(sessions) == 1
        assert sessions[0].channel == "slack"
        assert sessions[0].owner_uid == "user-a"
        assert sessions[0].session_id == "agent:main:slack:user-a"

    _run(scenario())


def test_supervisor_priority_chat_beats_heartbeat() -> None:
    processed: list[AgentEvent] = []

    async def record(_sup, event: AgentEvent, session: ChannelSession) -> None:
        processed.append(event)

    async def scenario() -> None:
        supervisor = SessionSupervisor("user-b", dispatch=record)
        heartbeat = AgentEvent(
            owner_uid="user-b", channel="heartbeat", kind=EventKind.HEARTBEAT
        )
        chat = AgentEvent(
            owner_uid="user-b",
            channel="web",
            kind=EventKind.CHAT_MESSAGE,
            payload={"text": "hi"},
        )
        # Enqueue both before starting the worker so priority order is tested
        # deterministically.
        await supervisor.enqueue(heartbeat)
        await supervisor.enqueue(chat)
        supervisor.start()
        for _ in range(200):
            if len(processed) >= 2:
                break
            await asyncio.sleep(0.01)
        await supervisor.stop()

    _run(scenario())
    assert [e.kind for e in processed] == [EventKind.CHAT_MESSAGE, EventKind.HEARTBEAT]


def test_supervisor_rejects_foreign_owner_event() -> None:
    async def scenario() -> None:
        supervisor = SessionSupervisor("user-c")
        with pytest.raises(ValueError):
            await supervisor.enqueue(
                AgentEvent(owner_uid="user-d", channel="web", kind=EventKind.CHAT_MESSAGE)
            )

    _run(scenario())


def test_registry_is_idempotent_and_isolates_owners() -> None:
    async def scenario() -> None:
        registry = SupervisorRegistry()
        try:
            s1a = await registry.get("user-1")
            s1b = await registry.get("user-1")
            s2 = await registry.get("user-2")
            assert s1a is s1b
            assert s1a is not s2
            assert len(registry) == 2
        finally:
            await registry.shutdown()

    _run(scenario())


def test_dispatcher_runs_per_event_and_counts_stats() -> None:
    counts: dict[str, int] = {"n": 0}

    async def counting(_sup, event: AgentEvent, session: ChannelSession) -> None:
        counts["n"] += 1

    async def scenario() -> None:
        supervisor = SessionSupervisor("user-e", dispatch=counting)
        supervisor.start()
        for i in range(5):
            await supervisor.enqueue(
                AgentEvent(
                    owner_uid="user-e",
                    channel="web",
                    kind=EventKind.CHAT_MESSAGE,
                    payload={"text": f"msg-{i}"},
                )
            )
        for _ in range(200):
            if counts["n"] >= 5:
                break
            await asyncio.sleep(0.01)
        await supervisor.stop()

    _run(scenario())
    assert counts["n"] == 5


def test_dispatcher_errors_do_not_crash_supervisor() -> None:
    async def boom(_sup, event: AgentEvent, session: ChannelSession) -> None:
        raise RuntimeError("simulated failure")

    async def scenario() -> None:
        supervisor = SessionSupervisor("user-f", dispatch=boom)
        supervisor.start()
        await supervisor.enqueue(
            AgentEvent(owner_uid="user-f", channel="web", kind=EventKind.CHAT_MESSAGE)
        )
        for _ in range(200):
            if supervisor.stats.errors >= 1:
                break
            await asyncio.sleep(0.01)
        await supervisor.stop()
        assert supervisor.stats.errors == 1
        assert supervisor.stats.enqueued == 1

    _run(scenario())


def test_event_priority_defaults_match_kind() -> None:
    chat = AgentEvent(owner_uid="u", channel="web", kind=EventKind.CHAT_MESSAGE)
    hb = AgentEvent(owner_uid="u", channel="heartbeat", kind=EventKind.HEARTBEAT)
    wh = AgentEvent(owner_uid="u", channel="webhook", kind=EventKind.WEBHOOK)
    assert chat.effective_priority() == EventPriority.USER_CHAT
    assert hb.effective_priority() == EventPriority.HEARTBEAT
    assert wh.effective_priority() == EventPriority.WEBHOOK
    forced = AgentEvent(
        owner_uid="u",
        channel="web",
        kind=EventKind.CHAT_MESSAGE,
        priority=EventPriority.BACKGROUND,
    )
    assert forced.effective_priority() == EventPriority.BACKGROUND


def test_channel_session_key_rejects_unknown_channel() -> None:
    with pytest.raises(ValueError):
        ChannelSessionKey(owner_uid="u", channel="bogus")
