"""WebSocket smoke test for /ws/navigate."""

from __future__ import annotations

from fastapi.testclient import TestClient

import main


class _StubOrchestrator:
    async def execute_task(self, session_id: str, instruction: str, on_step=None, on_frame=None, **kwargs):
        if on_frame:
            await on_frame("ZmFrZV9mcmFtZQ==")
        if on_step:
            await on_step({"type": "message", "content": f"stub:{instruction}"})
        return {"status": "completed", "session_id": session_id, "instruction": instruction}


def test_websocket_navigate_smoke() -> None:
    """WebSocket endpoint should stream frame, step, and final result."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        ws.send_json({"action": "navigate", "instruction": "hello"})
        frame = ws.receive_json()
        step = ws.receive_json()
        result = ws.receive_json()
        ws.send_json({"action": "stop"})

    assert frame["type"] == "frame"
    assert step["type"] == "step"
    assert result["type"] == "result"
    assert result["data"]["status"] == "completed"
