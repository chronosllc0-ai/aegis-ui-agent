"""WebSocket smoke and protocol validation tests for /ws/navigate."""

from __future__ import annotations

from fastapi.testclient import TestClient

import main


class _StubExecutor:
    async def ensure_browser(self) -> None:
        return None

    async def screenshot(self) -> bytes:
        return b"fake_png"

    @property
    def page(self):
        class _P:
            url = "about:blank"

            async def title(self) -> str:
                return "Blank"

        return _P()


class _StubOrchestrator:
    def __init__(self) -> None:
        self.executor = _StubExecutor()

    async def execute_task(self, session_id: str, instruction: str, on_step=None, **kwargs):
        if on_step:
            await on_step({"type": "message", "content": f"stub:{instruction}"})
        return {"status": "completed", "session_id": session_id, "instruction": instruction}


def test_websocket_navigate_smoke() -> None:
    """WebSocket endpoint should stream screenshot, step, and final result."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        initial = ws.receive_json()
        ws.send_json({"action": "navigate", "instruction": "hello"})
        frame = ws.receive_json()
        step = ws.receive_json()
        post_step_screenshot = ws.receive_json()
        result = ws.receive_json()
        ws.send_json({"action": "stop"})

    assert initial["type"] == "screenshot"
    assert step["type"] == "step"
    assert post_step_screenshot["type"] == "screenshot"
    assert result["type"] == "result"
    assert result["data"]["status"] == "completed"


def test_websocket_dequeue_invalid_index_payload_does_not_disconnect() -> None:
    """Malformed dequeue payload should return protocol error and keep socket open."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        ws.send_json({"action": "dequeue", "index": "not-a-number"})
        error = ws.receive_json()

        ws.send_json({"action": "queue", "instruction": "later"})
        queue_ack = ws.receive_json()
        ws.send_json({"action": "stop"})

    assert error["type"] == "error"
    assert error["data"]["message"] == "Invalid queue index"
    assert queue_ack["type"] == "step"
    assert "Queued instruction: later" in queue_ack["data"]["content"]
