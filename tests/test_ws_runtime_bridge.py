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
