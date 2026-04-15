"""Regression coverage for session routing metadata and lane queues."""

from __future__ import annotations

from backend.session_gateway import SessionEventHub, SessionRoute
from backend.session_lanes import QueuedInstruction, SessionLaneQueue


def test_session_gateway_uses_consistent_routing_key() -> None:
    hub = SessionEventHub()
    route = SessionRoute(session_id="sess-1", user_uid="user-1")

    payload_with_data = hub._envelope(route, {"type": "log", "data": {"value": 1}}, lane="interactive")
    payload_without_data = hub._envelope(route, {"type": "ping"}, lane="interactive")

    assert payload_with_data["routing"]["session_id"] == "sess-1"
    assert payload_without_data["routing"]["session_id"] == "sess-1"
    assert "_routing" not in payload_with_data["data"]


def test_session_lane_queue_pop_returns_queued_instruction() -> None:
    queue = SessionLaneQueue()
    queued = queue.enqueue("Ship the fix", lane="bot", source="slash_command", metadata={"command": "run"})

    popped = queue.pop()

    assert isinstance(popped, QueuedInstruction)
    assert popped.queue_id == queued.queue_id
    assert popped.instruction == "Ship the fix"
    assert popped.lane == "bot"
