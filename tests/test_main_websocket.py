"""WebSocket smoke and protocol validation tests for /ws/navigate."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

import main


class _StubExecutor:
    def __init__(self) -> None:
        self.page = type("PageStub", (), {"url": "https://example.com"})()

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


class _UserInputOrchestrator:
    """Stub orchestrator that pauses once for ask_user_input, then continues once."""

    def __init__(self) -> None:
        self.executor = _StubExecutor()
        self.execute_calls = 0
        self.responses: list[str] = []

    async def execute_task(self, session_id: str, instruction: str, on_step=None, on_user_input=None, **kwargs):
        self.execute_calls += 1
        if on_step:
            await on_step({"type": "message", "content": "before-user-input"})
        if on_user_input:
            response = await on_user_input("Proceed with which option?", ["Alpha", "Beta"])
            self.responses.append(response)
            if on_step:
                await on_step({"type": "message", "content": f"after-user-input:{response}"})
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


def test_initialize_database_falls_back_to_sqlite_for_local_postgres_driver_failure(monkeypatch) -> None:
    """Local PostgreSQL driver failures should transparently fall back to SQLite during dev."""
    previous_db_ready = main.db_ready
    previous_db_error = main.db_init_error
    state: dict[str, str | None] = {"url": None}
    init_calls: list[str | None] = []

    def fake_init_db(url: str | None) -> None:
        state["url"] = url
        init_calls.append(url)

    async def fake_create_tables() -> None:
        if state["url"]:
            raise ModuleNotFoundError("No module named 'asyncpg'")

    monkeypatch.setattr(main, "init_db", fake_init_db)
    monkeypatch.setattr(main, "create_tables", fake_create_tables)
    monkeypatch.setattr(main.settings, "DATABASE_URL", "postgresql://aegis:password@localhost:5432/aegis")
    monkeypatch.setattr(main.settings, "RAILWAY_ENVIRONMENT", "")
    main.db_ready = False
    main.db_init_error = None

    try:
        import asyncio

        asyncio.run(main._initialize_database())
        assert init_calls == ["postgresql://aegis:password@localhost:5432/aegis", None]
        assert main.db_ready is True
        assert main.db_init_error is None
    finally:
        main.db_ready = previous_db_ready
        main.db_init_error = previous_db_error


def test_websocket_user_input_response_resumes_single_pending_prompt_without_extra_task() -> None:
    """user_input_response should resolve one pending prompt and not start a second execute_task call."""
    orchestrator = _UserInputOrchestrator()
    main.orchestrator = orchestrator
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()  # initial frame
        ws.send_json({"action": "navigate", "instruction": "test user input flow"})

        before_step = ws.receive_json()
        user_input_request = ws.receive_json()
        request_id = user_input_request["data"]["request_id"]
        ws.send_json({"action": "user_input_response", "request_id": request_id, "response": "Alpha"})

        after_step = ws.receive_json()
        result = ws.receive_json()
        ws.send_json({"action": "stop"})

    assert before_step["type"] == "step"
    assert before_step["data"]["content"] == "before-user-input"
    assert user_input_request["type"] == "step"
    assert user_input_request["data"]["type"] == "user_input_request"
    assert after_step["type"] == "step"
    assert after_step["data"]["content"] == "after-user-input:Alpha"
    assert result["type"] == "result"
    assert result["data"]["instruction"] == "test user input flow"
    assert orchestrator.responses == ["Alpha"]
    assert len(orchestrator.responses) == 1
    assert orchestrator.execute_calls == 1


def test_websocket_user_input_response_logs_unknown_request_id(caplog) -> None:
    """Expired/unknown request IDs should be debug logged without side effects."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with caplog.at_level(logging.DEBUG):
        with client.websocket_connect("/ws/navigate") as ws:
            _ = ws.receive_json()
            ws.send_json({"action": "user_input_response", "request_id": "missing-request", "response": "ignored"})
            ws.send_json({"action": "stop"})

    assert "unknown/expired request_id=missing-request" in caplog.text
