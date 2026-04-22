"""End-to-end smoke test for the Phase 2 always-on runtime loop.

Covers every acceptance criterion from PLAN.md §Phase 2:

- a ``CHAT_MESSAGE`` enqueued on a :class:`SessionSupervisor`
- drains through the new dispatch hook
- triggers an agent turn against a stub :class:`Model`
- the agent calls a real native tool (``summarize_task``, which is
  filesystem-safe and DB-free)
- emits a final message
- writes run + events to an in-memory SQLite persistence layer
- fans out to a registered :class:`Subscriber`

The test deliberately does not hit any network, does not require a
provider API key, and does not touch the legacy Gemini path.
"""

from __future__ import annotations

import asyncio
import json
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
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base
from backend.runtime import AgentEvent, EventKind, SessionSupervisor
from backend.runtime.agent_loop import DispatchConfig, build_dispatch_hook
from backend.runtime.fanout import FanOutRegistry, RuntimeEvent, Subscriber
from backend.runtime.persistence import (
    RuntimeRun,
    RuntimeRunEvent,
    list_events,
)
from backend.runtime.tools.native import summarize_task


class _StubModel(Model):
    """Two-turn stub: turn 1 calls summarize_task, turn 2 finalises."""

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
                id="call_1",
                call_id="call_1",
                name="summarize_task",
                arguments=json.dumps({"content": "Hello world. This is a test.", "max_sentences": 1}),
                type="function_call",
            )
            return ModelResponse(output=[call], usage=Usage(), response_id="resp_1")
        msg = ResponseOutputMessage(
            id="msg_1",
            content=[
                ResponseOutputText(
                    type="output_text",
                    text="Summarised.",
                    annotations=[],
                )
            ],
            role="assistant",
            status="completed",
            type="message",
        )
        return ModelResponse(output=[msg], usage=Usage(), response_id="resp_2")

    async def stream_response(self, *args, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError


def _run(coro):
    return asyncio.run(coro)


def test_runtime_supervisor_end_to_end_smoke() -> None:
    """Drive a message through supervisor → agent → tool → fan-out + DB."""

    async def scenario() -> None:
        # ── isolated in-memory SQLite for persistence assertions ─────────
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        # ── fan-out subscriber collects every emitted event ──────────────
        received: list[RuntimeEvent] = []

        async def collector(event: RuntimeEvent) -> None:
            received.append(event)

        fanout = FanOutRegistry()

        # ── build the dispatch hook with a Stub Agent/Model override ─────
        def _build_agent(session, ctx):
            return Agent(
                name="aegis-test",
                instructions="test",
                tools=[summarize_task],
                model=_StubModel(),
            )

        hook = build_dispatch_hook(
            DispatchConfig(
                max_turns=4,
                fanout_registry=fanout,
                session_factory=session_factory,
                build_agent_fn=_build_agent,
            )
        )

        # ── spin up a supervisor with the real dispatch hook ─────────────
        supervisor = SessionSupervisor("smoke-user", dispatch=hook)
        supervisor.start()
        try:
            # Subscribe *before* dispatch so we catch every event.
            fan = await fanout.get("agent:main:web:smoke-user")
            await fan.subscribe(Subscriber(name="test", callback=collector))

            await supervisor.enqueue(
                AgentEvent(
                    owner_uid="smoke-user",
                    channel="web",
                    kind=EventKind.CHAT_MESSAGE,
                    payload={"text": "please summarize: Hello world. This is a test."},
                )
            )
            for _ in range(400):
                kinds = {ev.kind for ev in received}
                if "run_completed" in kinds:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail(
                    f"run never completed; received kinds={[e.kind for e in received]}"
                )
        finally:
            await supervisor.stop(drain=True)

        # ── assertions: fan-out covers the full timeline ─────────────────
        kinds = [ev.kind for ev in received]
        assert "run_started" in kinds, kinds
        assert "user_message" in kinds, kinds
        assert "tool_call" in kinds, kinds
        assert "final_message" in kinds, kinds
        assert "run_completed" in kinds, kinds

        # the tool_call event must carry the native tool's name
        tool_call_event = next(ev for ev in received if ev.kind == "tool_call")
        assert tool_call_event.payload.get("name") == "summarize_task"

        final_event = next(ev for ev in received if ev.kind == "final_message")
        assert "Summarised" in final_event.payload.get("text", "")

        # ── assertions: persistence ──────────────────────────────────────
        async with session_factory() as sess:
            runs_result = await sess.execute(
                RuntimeRun.__table__.select()
            )
            runs = runs_result.fetchall()
            assert len(runs) == 1, runs
            run_row = runs[0]._mapping
            run_id = run_row["id"]
            assert run_row["status"] == "completed"
            assert run_row["owner_uid"] == "smoke-user"

            events = await list_events(sess, run_id=run_id)
            persisted_kinds = [e.kind for e in events]
            assert "user_message" in persisted_kinds
            assert "tool_call" in persisted_kinds
            assert "final_message" in persisted_kinds
            assert "run_completed" in persisted_kinds

        await engine.dispose()

    _run(scenario())


def test_native_tool_manifest_covers_all_non_terminal_non_browser_tools() -> None:
    """Lock in the 42-tool parity contract with the legacy TOOL_DEFINITIONS."""

    from backend.runtime.tools.native import NATIVE_TOOL_NAMES
    from universal_navigator import TOOL_DEFINITIONS

    legacy = {t["name"] for t in TOOL_DEFINITIONS}
    terminal = {"done", "error"}
    browser = {"screenshot", "go_to_url", "click", "type_text", "scroll", "go_back", "wait"}
    expected = legacy - terminal - browser

    missing = expected - NATIVE_TOOL_NAMES
    extra = NATIVE_TOOL_NAMES - expected
    assert not missing, f"native.py missing legacy tools: {sorted(missing)}"
    assert not extra, f"native.py exposes unknown tools: {sorted(extra)}"
    assert len(NATIVE_TOOL_NAMES) == len(expected)
