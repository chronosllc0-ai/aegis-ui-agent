"""Phase 9: backend tests for the runtime FanOut → websocket bridge.

The dispatch hook in :mod:`backend.runtime.agent_loop` emits
``context_meter`` / ``compaction_checkpoint`` / ``final_message`` /
``run_completed`` etc. into a per-session :class:`FanOut`. Until
Phase 9 the FanOut had no subscribers and every event was dropped on
the floor (the chat WS only ever shipped a single
``{kind: \"accepted\"}`` ack). Phase 9 wires the WS to the FanOut.

These tests don't stand up a real FastAPI/WebSocket — they exercise
the helper directly with a fake websocket so the contract is locked
in without paying the import-graph cost.

Locked guarantees:

* :func:`_attach_runtime_event_bridge` returns the canonical runtime
  ``session_id`` in the form ``agent:main:web:{owner_uid}`` and a
  unique subscriber name keyed by the WS session id, then publishes a
  ``runtime_session`` announcement onto the websocket.
* When the FanOut publishes a runtime event for that session, the
  bridge forwards it as ``{type: \"runtime_event\", data: {...}}`` with
  ``kind`` / ``session_id`` / ``payload`` preserved.
* :func:`_detach_runtime_event_bridge` removes the subscriber so a
  subsequent publish does not double-deliver.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.runtime.fanout import FanOutRegistry, RuntimeEvent


class _FakeWebSocket:
    """Minimal async ``send_json`` capture surface for the bridge tests."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


@pytest.fixture(autouse=True)
def _isolate_runtime(monkeypatch):
    """Isolate the bridge tests from a real supervisor/registry.

    The bridge consults :mod:`backend.runtime.integration` to find the
    fan-out registry. We swap in a fresh :class:`FanOutRegistry` per
    test so subscribers don't leak between cases and we never depend on
    whether ``ensure_runtime_started`` was called by app startup.
    """
    import main

    fake_registry = FanOutRegistry()
    monkeypatch.setattr(main, "_runtime_get_fanout_registry", lambda: fake_registry)
    # Force the bridge on regardless of the env flag — the helper bails
    # early when ``_runtime_supervisor_enabled()`` returns False, but
    # for a unit test we want to assert the success path.
    monkeypatch.setattr(main, "_runtime_supervisor_enabled", lambda: True)

    # The bridge calls _safe_ws_send → websocket.send_json under the
    # hood. _safe_ws_send wraps a try/except that logs but never raises;
    # the FakeWebSocket above implements send_json so the wrapper is
    # happy.
    yield fake_registry


def test_attach_announces_runtime_session_and_returns_handles() -> None:
    import main

    async def scenario() -> None:
        ws = _FakeWebSocket()
        result = await main._attach_runtime_event_bridge(
            ws, ws_session_id="ws-abc", owner_uid="user-A"
        )
        assert result is not None
        runtime_session_id, subscriber_name = result
        assert runtime_session_id == "agent:main:web:user-A"
        assert subscriber_name == "ws:ws-abc"
        # The bridge announces the runtime session_id so the frontend
        # can hit /api/runtime/context-meter/{session_id} for hydration.
        announce = [m for m in ws.sent if m.get("type") == "runtime_session"]
        assert len(announce) == 1
        assert announce[0]["data"] == {
            "session_id": "agent:main:web:user-A",
            "owner_uid": "user-A",
            "channel": "web",
        }

    asyncio.run(scenario())


def test_publish_forwards_runtime_event_to_websocket(_isolate_runtime) -> None:
    import main

    fake_registry = _isolate_runtime

    async def scenario() -> None:
        ws = _FakeWebSocket()
        attached = await main._attach_runtime_event_bridge(
            ws, ws_session_id="ws-1", owner_uid="user-A"
        )
        assert attached is not None
        runtime_session_id, _ = attached
        fanout = await fake_registry.get(runtime_session_id)
        await fanout.publish(
            RuntimeEvent(
                kind="context_meter",
                session_id=runtime_session_id,
                owner_uid="user-A",
                channel="web",
                run_id="run-1",
                seq=4,
                payload={
                    "total_tokens": 1234,
                    "projected_pct": 12.5,
                    "should_compact": False,
                    "buckets": [],
                },
            )
        )
        forwarded = [m for m in ws.sent if m.get("type") == "runtime_event"]
        assert len(forwarded) == 1, ws.sent
        body = forwarded[0]["data"]
        assert body["kind"] == "context_meter"
        assert body["session_id"] == runtime_session_id
        assert body["owner_uid"] == "user-A"
        assert body["channel"] == "web"
        assert body["run_id"] == "run-1"
        assert body["seq"] == 4
        # Bucket payload passes through verbatim — the frontend reads
        # the same shape the dispatch hook builds.
        assert body["payload"]["total_tokens"] == 1234
        assert body["payload"]["projected_pct"] == 12.5
        assert body["payload"]["should_compact"] is False

    asyncio.run(scenario())


def test_detach_removes_subscriber_and_stops_forwarding(_isolate_runtime) -> None:
    import main

    fake_registry = _isolate_runtime

    async def scenario() -> None:
        ws = _FakeWebSocket()
        attached = await main._attach_runtime_event_bridge(
            ws, ws_session_id="ws-2", owner_uid="user-B"
        )
        assert attached is not None
        runtime_session_id, subscriber_name = attached
        fanout = await fake_registry.get(runtime_session_id)
        await main._detach_runtime_event_bridge(runtime_session_id, subscriber_name)
        # After detach, publishing must not append another runtime_event.
        before = len([m for m in ws.sent if m.get("type") == "runtime_event"])
        await fanout.publish(
            RuntimeEvent(
                kind="final_message",
                session_id=runtime_session_id,
                owner_uid="user-B",
                channel="web",
                run_id="run-2",
                seq=10,
                payload={"text": "this should not be delivered"},
            )
        )
        after = len([m for m in ws.sent if m.get("type") == "runtime_event"])
        assert before == after

    asyncio.run(scenario())


def test_attach_returns_none_when_supervisor_disabled(monkeypatch) -> None:
    import main

    monkeypatch.setattr(main, "_runtime_supervisor_enabled", lambda: False)
    ws = _FakeWebSocket()
    result = asyncio.run(
        main._attach_runtime_event_bridge(
            ws, ws_session_id="ws-x", owner_uid="user-X"
        )
    )
    assert result is None
    # When the bridge bails early it must not announce a runtime_session
    # — otherwise the frontend would try to hydrate a meter that the
    # backend isn't even servicing on this deployment.
    assert all(m.get("type") != "runtime_session" for m in ws.sent)


# ── Phase 10: bridge persists assistant final_message into chat log ──


class _FakeRuntime:
    """Minimal stand-in for ``SessionRuntime`` used in the persistence tests.

    Only the attributes the bridge persistence path reads (``user_uid``)
    are exercised; the rest is irrelevant because we monkeypatch
    ``_log_web_message`` itself to a capture fn.
    """

    def __init__(self, user_uid: str | None) -> None:
        self.user_uid = user_uid
        self.current_request_id: str | None = None
        self.current_task_id: str | None = None
        self.conversation_id: str | None = None


@pytest.fixture(autouse=True)
def _reset_dedupe():
    """Each test starts with a fresh dedupe set so cross-test runs of
    the same ``run_id`` don't accidentally suppress a write.
    """
    import main

    main._runtime_persistence_reset_for_tests()
    yield
    main._runtime_persistence_reset_for_tests()


def test_final_message_is_persisted_for_authenticated_web_session(
    _isolate_runtime, monkeypatch
) -> None:
    """final_message events route into ``_log_web_message`` so refresh
    sees the assistant reply. Without this, Phase 10's chat-from-runtime
    rendering would be live-only — every reconnect would lose the bot
    half of the conversation, breaking the "always-on" promise.
    """
    import main

    fake_registry = _isolate_runtime
    captured: list[dict] = []

    async def fake_log(runtime, session_id, role, content, *, title=None, metadata=None, title_candidate=None):
        captured.append(
            {
                "session_id": session_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
            }
        )

    monkeypatch.setattr(main, "_log_web_message", fake_log)

    runtime = _FakeRuntime(user_uid="user-A")

    async def scenario() -> None:
        ws = _FakeWebSocket()
        attached = await main._attach_runtime_event_bridge(
            ws, ws_session_id="ws-final", owner_uid="user-A", runtime=runtime
        )
        assert attached is not None
        runtime_session_id, _ = attached
        fanout = await fake_registry.get(runtime_session_id)
        await fanout.publish(
            RuntimeEvent(
                kind="final_message",
                session_id=runtime_session_id,
                owner_uid="user-A",
                channel="web",
                run_id="run-final",
                seq=42,
                payload={"text": "Hello from the runtime."},
            )
        )

    asyncio.run(scenario())

    assert len(captured) == 1, captured
    entry = captured[0]
    assert entry["role"] == "assistant"
    assert entry["content"] == "Hello from the runtime."
    assert entry["session_id"] == "ws-final"
    assert entry["metadata"]["source"] == "runtime"
    assert entry["metadata"]["action"] == "final_message"
    assert entry["metadata"]["run_id"] == "run-final"


def test_final_message_skipped_for_anonymous_session(
    _isolate_runtime, monkeypatch
) -> None:
    """Anonymous sessions (no ``user_uid``) must not hit the chat
    persistence path — ``_log_web_message`` early-returns on missing
    uid anyway, but doing the runtime call would still pull a DB
    handle just to drop it. The bridge guards before the call so the
    DB pool stays free for authenticated traffic.
    """
    import main

    fake_registry = _isolate_runtime
    captured: list[dict] = []

    async def fake_log(*args, **kwargs):
        captured.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(main, "_log_web_message", fake_log)

    runtime = _FakeRuntime(user_uid=None)

    async def scenario() -> None:
        ws = _FakeWebSocket()
        attached = await main._attach_runtime_event_bridge(
            ws, ws_session_id="ws-anon", owner_uid="anon-session", runtime=runtime
        )
        assert attached is not None
        runtime_session_id, _ = attached
        fanout = await fake_registry.get(runtime_session_id)
        await fanout.publish(
            RuntimeEvent(
                kind="final_message",
                session_id=runtime_session_id,
                owner_uid="anon-session",
                channel="web",
                run_id="run-anon",
                seq=1,
                payload={"text": "anonymous run output"},
            )
        )

    asyncio.run(scenario())
    assert captured == []


def test_final_message_persistence_dedupes_per_run_across_bridges(
    _isolate_runtime, monkeypatch
) -> None:
    """Multi-tab dedupe — codex P1 follow-up from PR #345 review.

    Authenticated web sessions share a single per-user runtime FanOut
    (``agent:main:web:{owner_uid}``). Every tab attaches its own
    bridge; without a process-global dedupe each bridge would persist
    the same ``final_message``, so a 2-tab user would see the
    assistant reply duplicated in their chat history. The dedupe set
    is keyed on ``run_id``: the first bridge to handle the event
    wins, the rest skip.
    """
    import main

    fake_registry = _isolate_runtime
    main._runtime_persistence_reset_for_tests()
    captured: list[dict] = []

    async def fake_log(runtime, session_id, role, content, *, title=None, metadata=None, title_candidate=None):
        captured.append({"session_id": session_id, "role": role, "content": content, "metadata": metadata or {}})

    monkeypatch.setattr(main, "_log_web_message", fake_log)

    runtime_a = _FakeRuntime(user_uid="user-A")
    runtime_b = _FakeRuntime(user_uid="user-A")

    async def scenario() -> None:
        ws_a = _FakeWebSocket()
        ws_b = _FakeWebSocket()
        attached_a = await main._attach_runtime_event_bridge(
            ws_a, ws_session_id="ws-tab-A", owner_uid="user-A", runtime=runtime_a
        )
        attached_b = await main._attach_runtime_event_bridge(
            ws_b, ws_session_id="ws-tab-B", owner_uid="user-A", runtime=runtime_b
        )
        assert attached_a is not None and attached_b is not None
        runtime_session_id, _ = attached_a
        # Both tabs share the same FanOut — that's the whole point of
        # the per-user runtime model.
        assert attached_b[0] == runtime_session_id
        fanout = await fake_registry.get(runtime_session_id)
        await fanout.publish(
            RuntimeEvent(
                kind="final_message",
                session_id=runtime_session_id,
                owner_uid="user-A",
                channel="web",
                run_id="run-multitab",
                seq=7,
                payload={"text": "shared reply", "ws_session_id": "ws-tab-A"},
            )
        )

    asyncio.run(scenario())

    # Exactly one persistence write despite two attached bridges.
    assert len(captured) == 1, captured
    entry = captured[0]
    # And the write lands on the *originating* tab's session, not on
    # whichever bridge happened to fire second.
    assert entry["session_id"] == "ws-tab-A"
    assert entry["metadata"]["origin_ws_session_id"] == "ws-tab-A"
    assert entry["metadata"]["run_id"] == "run-multitab"


def test_final_message_uses_origin_ws_session_id_when_bridge_differs(
    _isolate_runtime, monkeypatch
) -> None:
    """Cross-tab targeting — codex P1 follow-up from PR #345 review.

    Even with dedupe, if the *only* bridge to receive the event is
    not the originating tab (e.g. the originating tab disconnected
    between dispatch and final), the persistence path must still
    target the originating ``ws_session_id`` so the reply ends up in
    the correct chat session row, not the bystander tab's session.
    """
    import main

    fake_registry = _isolate_runtime
    main._runtime_persistence_reset_for_tests()
    captured: list[dict] = []

    async def fake_log(runtime, session_id, role, content, *, title=None, metadata=None, title_candidate=None):
        captured.append({"session_id": session_id, "metadata": metadata or {}})

    monkeypatch.setattr(main, "_log_web_message", fake_log)

    runtime = _FakeRuntime(user_uid="user-A")

    async def scenario() -> None:
        ws = _FakeWebSocket()
        attached = await main._attach_runtime_event_bridge(
            ws, ws_session_id="ws-bystander", owner_uid="user-A", runtime=runtime
        )
        assert attached is not None
        runtime_session_id, _ = attached
        fanout = await fake_registry.get(runtime_session_id)
        await fanout.publish(
            RuntimeEvent(
                kind="final_message",
                session_id=runtime_session_id,
                owner_uid="user-A",
                channel="web",
                run_id="run-cross",
                seq=3,
                payload={"text": "reply for the originator", "ws_session_id": "ws-originator"},
            )
        )

    asyncio.run(scenario())
    assert len(captured) == 1
    assert captured[0]["session_id"] == "ws-originator"
    assert captured[0]["metadata"]["origin_ws_session_id"] == "ws-originator"


def test_final_message_falls_back_to_bridge_session_when_origin_missing(
    _isolate_runtime, monkeypatch
) -> None:
    """If the runtime event omits ``ws_session_id`` (legacy producer
    or non-chat-originated runs) the persistence path falls back to
    the bridge's own ``ws_session_id`` — never silently drops the
    write.
    """
    import main

    fake_registry = _isolate_runtime
    main._runtime_persistence_reset_for_tests()
    captured: list[dict] = []

    async def fake_log(runtime, session_id, role, content, *, title=None, metadata=None, title_candidate=None):
        captured.append({"session_id": session_id, "metadata": metadata or {}})

    monkeypatch.setattr(main, "_log_web_message", fake_log)

    runtime = _FakeRuntime(user_uid="user-A")

    async def scenario() -> None:
        ws = _FakeWebSocket()
        attached = await main._attach_runtime_event_bridge(
            ws, ws_session_id="ws-self", owner_uid="user-A", runtime=runtime
        )
        assert attached is not None
        runtime_session_id, _ = attached
        fanout = await fake_registry.get(runtime_session_id)
        await fanout.publish(
            RuntimeEvent(
                kind="final_message",
                session_id=runtime_session_id,
                owner_uid="user-A",
                channel="web",
                run_id="run-legacy",
                seq=1,
                payload={"text": "legacy producer reply"},  # no ws_session_id
            )
        )

    asyncio.run(scenario())
    assert len(captured) == 1
    assert captured[0]["session_id"] == "ws-self"
    assert captured[0]["metadata"]["origin_ws_session_id"] == "ws-self"


def test_final_message_skipped_for_non_web_channel(
    _isolate_runtime, monkeypatch
) -> None:
    """Slack / Telegram / heartbeat dispatches share the runtime
    fan-out (one session per user across surfaces, per Phase 7) but
    their assistant replies are persisted by their respective egress
    workers, not the web chat log. The bridge filters to ``channel ==
    "web"`` so a Slack final_message doesn't double-write into the web
    chat history.
    """
    import main

    fake_registry = _isolate_runtime
    captured: list[dict] = []

    async def fake_log(*args, **kwargs):
        captured.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(main, "_log_web_message", fake_log)

    runtime = _FakeRuntime(user_uid="user-A")

    async def scenario() -> None:
        ws = _FakeWebSocket()
        attached = await main._attach_runtime_event_bridge(
            ws, ws_session_id="ws-mixed", owner_uid="user-A", runtime=runtime
        )
        assert attached is not None
        runtime_session_id, _ = attached
        fanout = await fake_registry.get(runtime_session_id)
        await fanout.publish(
            RuntimeEvent(
                kind="final_message",
                session_id=runtime_session_id,
                owner_uid="user-A",
                channel="slack",
                run_id="run-slack",
                seq=2,
                payload={"text": "this came from slack"},
            )
        )

    asyncio.run(scenario())
    assert captured == []


# ── Hotfix 2026-04-28: bridge must stop pushing into a closed socket ──

class _ClosedFakeWebSocket(_FakeWebSocket):
    """``_FakeWebSocket`` whose ``client_state`` is ``DISCONNECTED``.

    Mirrors the post-disconnect state Starlette / FastAPI leaves a
    ``WebSocket`` in: the consumer side has observed the close frame
    but the bridge subscriber may still receive frames from the
    per-user runtime FanOut for milliseconds afterwards. Without the
    hotfix, every push into this socket triggers
    ``RuntimeError: Unexpected ASGI message 'websocket.send', after
    sending 'websocket.close'`` which the old ``_safe_ws_send`` logged
    via ``logger.exception`` (full traceback) and then continued — at
    rates of ~10 frames/sec from heartbeat dispatches that overwhelmed
    Railway's 500 logs/sec replica cap and got the container killed.
    """

    def __init__(self) -> None:
        super().__init__()
        from starlette.websockets import WebSocketState
        self.client_state = WebSocketState.DISCONNECTED
        self.application_state = WebSocketState.DISCONNECTED


def test_bridge_evicts_subscriber_when_socket_already_closed(
    _isolate_runtime,
) -> None:
    """The runtime fan-out subscriber raises on a disconnected socket so
    ``FanOut`` auto-evicts it. A subsequent publish to the same fan-out
    must not deliver to the dead subscriber.
    """
    import main

    fake_registry = _isolate_runtime

    async def scenario() -> None:
        ws = _ClosedFakeWebSocket()
        attached = await main._attach_runtime_event_bridge(
            ws, ws_session_id="ws-dead", owner_uid="user-A"
        )
        # ``_attach_runtime_event_bridge`` itself calls
        # ``_safe_ws_send`` to announce the runtime_session — that
        # short-circuits silently because client_state is DISCONNECTED,
        # so the announcement frame is dropped (no traceback logged).
        # The subscription is still attached, however; publishing a
        # frame should raise out of the callback and FanOut should
        # remove the subscriber.
        assert attached is not None
        runtime_session_id, subscriber_name = attached
        fanout = await fake_registry.get(runtime_session_id)
        # First publish triggers the eviction.
        await fanout.publish(
            RuntimeEvent(
                kind="context_meter",
                session_id=runtime_session_id,
                owner_uid="user-A",
                channel="web",
                run_id=None,
                seq=1,
                payload={"projected_pct": 12.5},
            )
        )
        # Second publish must be a no-op — subscriber should be gone.
        # We assert by checking ``FanOut.__len__`` (number of live
        # subscribers) and the private ``_subscribers`` list — the
        # eviction guarantee is that ``subscriber_name`` is no longer
        # present after a callback raises.
        remaining = [s.name for s in fanout._subscribers]  # type: ignore[attr-defined]
        assert subscriber_name not in remaining, (
            f"subscriber {subscriber_name!r} should have been evicted "
            f"after the closed-socket push raised; still present in "
            f"{remaining!r}"
        )
        # Belt-and-braces: a second publish must not raise either.
        await fanout.publish(
            RuntimeEvent(
                kind="context_meter",
                session_id=runtime_session_id,
                owner_uid="user-A",
                channel="web",
                run_id=None,
                seq=2,
                payload={"projected_pct": 13.0},
            )
        )

    asyncio.run(scenario())


def test_safe_ws_send_short_circuits_on_disconnected_socket() -> None:
    """``_safe_ws_send`` returns ``False`` without calling ``send_json``
    when the websocket has already moved to ``DISCONNECTED``.
    """
    import main

    class _ExplodingWebSocket(_ClosedFakeWebSocket):
        async def send_json(self, payload):  # type: ignore[override]
            raise AssertionError(
                "send_json must not be invoked on a DISCONNECTED socket; "
                "the fast-path in _safe_ws_send is the whole point of the "
                "2026-04-28 hotfix"
            )

    async def scenario() -> None:
        ws = _ExplodingWebSocket()
        sent = await main._safe_ws_send(
            ws,
            {"type": "runtime_event", "data": {}},
            ws_session_id="ws-dead",
            phase="runtime_event_forward",
        )
        assert sent is False

    asyncio.run(scenario())
