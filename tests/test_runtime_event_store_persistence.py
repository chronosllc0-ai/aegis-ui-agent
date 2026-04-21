"""Runtime event store persistence and session-scoped pagination tests."""

from __future__ import annotations

from pathlib import Path

from backend.runtime_telemetry import RuntimeEventStore


def test_runtime_event_store_persists_and_hydrates(tmp_path: Path) -> None:
    """Events should persist to disk and be available after rehydration."""
    store_path = tmp_path / "runtime_events.jsonl"
    store = RuntimeEventStore(ttl_seconds=3600, max_events=100, persistence_path=store_path)
    store.append(
        category="websocket_lifecycle",
        subsystem="websocket",
        level="info",
        message="websocket session opened",
        session_id="sess-1",
    )
    store.append(
        category="heartbeat",
        subsystem="heartbeat",
        level="info",
        message="heartbeat instruction queued",
        session_id="sess-1",
    )

    rehydrated = RuntimeEventStore(ttl_seconds=3600, max_events=100, persistence_path=store_path)
    events = rehydrated.list_events(session_id="sess-1", limit=50)["events"]
    assert len(events) == 2
    assert events[0]["category"] == "heartbeat"
    assert events[1]["category"] == "websocket_lifecycle"


def test_runtime_event_store_session_pagination(tmp_path: Path) -> None:
    """Pagination should stay consistent when scoped to a session."""
    store = RuntimeEventStore(ttl_seconds=3600, max_events=100, persistence_path=tmp_path / "events.jsonl")
    for idx in range(6):
        store.append(
            category="queue_steer_runtime",
            subsystem="runtime",
            level="info",
            message=f"event-{idx}",
            session_id="sess-2" if idx < 5 else "sess-3",
        )

    page_1 = store.list_events(session_id="sess-2", limit=2, cursor=0)
    page_2 = store.list_events(session_id="sess-2", limit=2, cursor=2)

    assert page_1["pagination"]["total"] == 5
    assert page_1["pagination"]["has_more"] is True
    assert len(page_1["events"]) == 2
    assert len(page_2["events"]) == 2
