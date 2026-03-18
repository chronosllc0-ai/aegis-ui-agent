"""WebSocket smoke and protocol validation tests for /ws/navigate."""

from __future__ import annotations

from fastapi.testclient import TestClient

import main


class _StubExecutor:
    async def ensure_browser(self) -> None:
        return None

    async def screenshot(self) -> bytes:
        return b"fake_png"


class _StubOrchestrator:
    def __init__(self) -> None:
        self.executor = _StubExecutor()

    async def execute_task(self, session_id: str, instruction: str, on_step=None, on_frame=None, on_workflow_step=None, **kwargs):
        if on_step:
            await on_step({"type": "message", "content": f"stub:{instruction}"})
        if on_frame:
            await on_frame("ZmFrZV9mcmFtZQ==")
        if on_workflow_step:
            await on_workflow_step(
                {
                    "step_id": "step-1",
                    "parent_step_id": None,
                    "action": "navigate",
                    "description": "stub step",
                    "status": "completed",
                    "timestamp": "2026-03-10T10:12:02Z",
                    "duration_ms": 10,
                    "screenshot": None,
                }
            )
        return {"status": "completed", "session_id": session_id, "instruction": instruction}


def test_websocket_navigate_smoke() -> None:
    """WebSocket endpoint should stream frame, step, and final result."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        initial = ws.receive_json()
        ws.send_json({"action": "navigate", "instruction": "hello"})
        step = ws.receive_json()
        frame = ws.receive_json()
        workflow_step = ws.receive_json()
        result = ws.receive_json()
        ws.send_json({"action": "stop"})

    assert initial["type"] == "frame"
    assert step["type"] == "step"
    assert frame["type"] == "frame"
    assert workflow_step["type"] == "workflow_step"
    assert result["type"] == "result"
    assert result["data"]["status"] == "completed"


def test_websocket_dequeue_invalid_index_payload_does_not_disconnect() -> None:
    """Malformed dequeue payload should return protocol error and keep socket open."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "dequeue", "index": "not-a-number"})
        error = ws.receive_json()

        ws.send_json({"action": "queue", "instruction": "later"})
        queue_ack = ws.receive_json()
        ws.send_json({"action": "stop"})

    assert error["type"] == "error"
    assert error["data"]["message"] == "Invalid queue index"
    assert queue_ack["type"] == "step"
    assert "Queued instruction: later" in queue_ack["data"]["content"]


def test_health_reports_initializing_database_state() -> None:
    """Health endpoint should stay available while the database is still warming up."""
    previous_db_ready = main.db_ready
    previous_db_error = main.db_init_error
    main.db_ready = False
    main.db_init_error = "connection refused"

    client = TestClient(main.app)
    response = client.get("/health")

    main.db_ready = previous_db_ready
    main.db_init_error = previous_db_error

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "initializing"
    assert response.json()["database_error"] == "connection refused"
