"""WebSocket smoke and protocol validation tests for /ws/navigate."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

import main


def _recv_until_type(ws, event_type: str, max_messages: int = 20) -> dict[str, object]:
    """Read websocket events until a matching `type` is found."""
    for _ in range(max_messages):
        payload = ws.receive_json()
        if payload.get("type") == event_type:
            return payload
    raise AssertionError(f"Did not receive event type '{event_type}' within {max_messages} messages")


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


class _StreamingNormalizationOrchestrator:
    """Stub orchestrator that emits escaped newlines and chunked reasoning deltas."""

    def __init__(self) -> None:
        self.executor = _StubExecutor()

    async def execute_task(self, session_id: str, instruction: str, on_step=None, on_reasoning_delta=None, **kwargs):
        if on_step:
            await on_step({"type": "message", "content": "start\\nline\\r\\nnext"})
            await on_step({"type": "reasoning_start", "step_id": "r1", "content": "[thinking]"})
        if on_reasoning_delta:
            await on_reasoning_delta("r1", "part\\n")
            await on_reasoning_delta("r1", "two")
        if on_step:
            await on_step({"type": "reasoning", "step_id": "r1", "content": "[reasoning] part\\ntwo"})
            await on_step({"type": "result", "content": "done"})
        return {"status": "completed", "session_id": session_id, "instruction": instruction}


class _HandoffOrchestrator:
    """Stub orchestrator that blocks on handoff_to_user then resumes once."""

    def __init__(self) -> None:
        self.executor = _StubExecutor()
        self.resume_count = 0

    async def execute_task(self, session_id: str, instruction: str, on_step=None, on_handoff_to_user=None, **kwargs):
        if on_step:
            await on_step({"type": "message", "content": "before-handoff"})
        if on_handoff_to_user:
            result = await on_handoff_to_user(
                "CAPTCHA detected",
                "Solve the CAPTCHA, then click Continue.",
                "Continue after CAPTCHA",
                "handoff-req-1",
            )
            self.resume_count += 1
            if on_step:
                await on_step({"type": "message", "content": f"after-handoff:{result}"})
        return {"status": "completed", "session_id": session_id, "instruction": instruction}


def test_navigate_start_always_receives_ack() -> None:
    """navigate_start should always return navigate_ack before execution updates."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)
    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "navigate_start", "request_id": "req-ack-1", "instruction": "hello"})
        ack = ws.receive_json()
        ws.send_json({"action": "stop_task"})
    assert ack["type"] == "navigate_ack"
    assert ack["data"]["request_id"] == "req-ack-1"
    assert ack["data"]["accepted"] is True


def test_rejected_start_returns_error_and_socket_remains_open() -> None:
    """Invalid start payloads should emit task_error and keep the socket open."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)
    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "navigate_start", "request_id": "req-bad-1", "instruction": ""})
        ack = ws.receive_json()
        err = ws.receive_json()
        ws.send_json({"action": "ping"})
        pong = ws.receive_json()
    assert ack["type"] == "navigate_ack"
    assert ack["data"]["accepted"] is False
    assert err["type"] == "task_error"
    assert err["data"]["code"] == "E_BAD_PAYLOAD"
    assert pong["type"] == "pong"


def test_terminal_event_always_emitted() -> None:
    """A started task should always emit terminal task_result or task_error."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)
    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "navigate_start", "request_id": "req-terminal-1", "instruction": "hello"})
        terminal = None
        for _ in range(10):
            message = ws.receive_json()
            if message.get("type") in {"task_result", "task_error"}:
                terminal = message
                break
        ws.send_json({"action": "stop_task"})
    assert terminal is not None
    assert terminal["type"] in {"task_result", "task_error"}


def test_duplicate_request_id_returns_same_ack_task_id() -> None:
    """Duplicate request IDs should return the same idempotent ack payload."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)
    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "navigate_start", "request_id": "req-dupe-1", "instruction": "hello"})
        ack1 = _recv_until_type(ws, "navigate_ack")
        ws.send_json({"action": "navigate_start", "request_id": "req-dupe-1", "instruction": "hello again"})
        ack2 = _recv_until_type(ws, "navigate_ack")
        ws.send_json({"action": "stop_task"})
    assert ack1["type"] == "navigate_ack"
    assert ack2["type"] == "navigate_ack"
    assert ack1["data"]["task_id"] == ack2["data"]["task_id"]
    assert ack2["data"]["request_id"] == "req-dupe-1"


def test_websocket_navigate_smoke() -> None:
    """WebSocket endpoint should stream frame, step, and final result."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        initial = ws.receive_json()
        ws.send_json({"action": "navigate_start", "request_id": "req-smoke", "instruction": "hello"})
        received: list[dict[str, object]] = []
        while True:
            event = ws.receive_json()
            received.append(event)
            if event.get("type") == "result":
                break
        ws.send_json({"action": "stop_task"})

    assert initial["type"] == "frame"
    assert any(evt.get("type") == "navigate_ack" for evt in received)
    assert any(evt.get("type") == "task_state" for evt in received)
    assert any(evt.get("type") == "step" for evt in received)
    assert any(evt.get("type") == "frame" for evt in received)
    assert any(evt.get("type") == "workflow_step" for evt in received)
    result = next(evt for evt in received if evt.get("type") == "result")
    assert result["data"]["status"] == "completed"


def test_websocket_navigate_requires_instruction_and_keeps_socket_open() -> None:
    """Empty navigate instructions should return a protocol error without disconnecting."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "navigate", "instruction": "   "})
        ack = ws.receive_json()
        error = ws.receive_json()

        ws.send_json({"action": "navigate", "instruction": "hello after error"})
        events: list[dict[str, object]] = []
        while True:
            event = ws.receive_json()
            events.append(event)
            if event.get("type") == "result":
                break
        ws.send_json({"action": "stop_task"})

    assert ack["type"] == "navigate_ack"
    assert ack["data"]["accepted"] is False
    assert error["type"] == "task_error"
    assert error["data"]["code"] == "E_BAD_PAYLOAD"
    assert any(evt.get("type") == "step" for evt in events)
    assert any(evt.get("type") == "result" for evt in events)


def test_websocket_dequeue_invalid_index_payload_does_not_disconnect() -> None:
    """Disabled runtime-control payload should return protocol error and keep socket open."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "dequeue", "index": "not-a-number"})
        error = ws.receive_json()

        ws.send_json({"action": "ping"})
        queue_ack = ws.receive_json()
        ws.send_json({"action": "stop_task"})

    assert error["type"] == "task_error"
    assert "disabled" in error["data"]["message"].lower()
    assert queue_ack["type"] == "pong"


def test_idle_steer_requires_navigate_when_no_task_is_running() -> None:
    """Steer action should be rejected while idle; navigate is the sole start action."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "steer", "instruction": "open example.com"})
        error = ws.receive_json()
        ws.send_json({"action": "navigate", "instruction": "open example.com"})
        step = ws.receive_json()
        ws.send_json({"action": "stop"})

    assert error["type"] == "task_error"
    assert "disabled" in error["data"]["message"].lower()
    assert step["type"] in {"navigate_ack", "task_state", "step"}


def test_idle_queue_requires_navigate_when_no_task_is_running() -> None:
    """Queue action should be rejected while idle; navigate is the sole start action."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "queue", "instruction": "search for laptops"})
        error = ws.receive_json()
        ws.send_json({"action": "navigate", "instruction": "search for laptops"})
        step = ws.receive_json()
        ws.send_json({"action": "stop"})

    assert error["type"] == "task_error"
    assert "disabled" in error["data"]["message"].lower()
    assert step["type"] in {"navigate_ack", "task_state", "step"}


def test_navigate_accepts_prompt_alias_when_instruction_missing() -> None:
    """Navigate should accept a `prompt` field for compatibility with prompt-centric clients."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "navigate", "prompt": "open docs homepage"})
        _ = _recv_until_type(ws, "navigate_ack")
        step = _recv_until_type(ws, "step")
        ws.send_json({"action": "stop"})

    assert step["type"] == "step"
    assert step["data"]["content"] == "stub:open docs homepage"


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

        before_step = _recv_until_type(ws, "step")
        user_input_request = _recv_until_type(ws, "step")
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


def test_handoff_request_pauses_and_continues_once() -> None:
    """handoff_continue should resume exactly once after handoff_request."""
    orchestrator = _HandoffOrchestrator()
    main.orchestrator = orchestrator
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "navigate_start", "request_id": "req-handoff-1", "instruction": "login"})
        _ = _recv_until_type(ws, "navigate_ack")
        _ = _recv_until_type(ws, "step")  # before-handoff
        handoff_step = _recv_until_type(ws, "step")
        assert handoff_step["data"]["type"] == "handoff_request"
        assert handoff_step["data"]["request_id"] == "handoff-req-1"
        ws.send_json({"action": "handoff_continue", "request_id": "handoff-req-1"})
        completion_step = _recv_until_type(ws, "step")
        resumed_step = _recv_until_type(ws, "step")
        result = _recv_until_type(ws, "result")
        ws.send_json({"action": "stop_task"})

    assert completion_step["data"]["content"] == "Human handoff completed. Resuming agent."
    assert resumed_step["data"]["content"].startswith("after-handoff:")
    assert result["data"]["status"] == "completed"
    assert orchestrator.resume_count == 1


def test_human_browser_action_rejected_without_active_handoff() -> None:
    """human_browser_action should fail with E_BAD_PAYLOAD when no handoff is active."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)
    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "human_browser_action", "kind": "click", "x": 100, "y": 100})
        error = _recv_until_type(ws, "task_error")
        ws.send_json({"action": "stop_task"})
    assert error["data"]["code"] == "E_BAD_PAYLOAD"
    assert "handoff is not active" in error["data"]["message"]


def test_human_browser_action_rejects_malformed_payload_during_handoff() -> None:
    """Malformed action payloads should be rejected even when handoff is active."""
    main.orchestrator = _HandoffOrchestrator()
    client = TestClient(main.app)
    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "navigate_start", "request_id": "req-handoff-2", "instruction": "login"})
        _ = _recv_until_type(ws, "navigate_ack")
        _ = _recv_until_type(ws, "step")
        _ = _recv_until_type(ws, "step")  # handoff_request
        ws.send_json({"action": "human_browser_action", "kind": "click", "x": "bad", "y": 100})
        error = _recv_until_type(ws, "task_error")
        ws.send_json({"action": "handoff_continue", "request_id": "handoff-req-1"})
        _ = _recv_until_type(ws, "result")
        ws.send_json({"action": "stop_task"})
    assert error["data"]["code"] == "E_BAD_PAYLOAD"
    assert "rejected" in error["data"]["message"]


def test_websocket_stream_normalizes_steps_and_reasoning_deltas_incrementally() -> None:
    """Step and reasoning stream payloads should normalize escaped newlines during streaming."""
    main.orchestrator = _StreamingNormalizationOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()  # initial frame
        ws.send_json({"action": "navigate", "instruction": "normalize stream"})
        _ = _recv_until_type(ws, "navigate_ack")
        step1 = _recv_until_type(ws, "step")
        step2 = _recv_until_type(ws, "step")
        delta1 = _recv_until_type(ws, "reasoning_delta")
        delta2 = _recv_until_type(ws, "reasoning_delta")
        step3 = _recv_until_type(ws, "step")
        step4 = _recv_until_type(ws, "step")
        result = _recv_until_type(ws, "result")
        ws.send_json({"action": "stop"})

    assert step1["type"] == "step"
    assert step1["data"]["content"] == "start\nline\nnext"
    assert step2["data"]["type"] == "reasoning_start"
    assert delta1["type"] == "reasoning_delta"
    assert delta1["data"]["delta"] == "part\n"
    assert delta2["data"]["delta"] == "two"
    assert step3["data"]["type"] == "reasoning"
    assert step3["data"]["content"] == "[reasoning] part\ntwo"
    assert step4["data"]["content"] == "done"
    assert result["type"] == "result"


def test_websocket_config_resolves_server_authoritative_skill_ids(monkeypatch) -> None:
    """Config action should persist server-resolved skill IDs instead of trusting client list."""
    class _CapturingOrchestrator(_StubOrchestrator):
        def __init__(self) -> None:
            super().__init__()
            self.last_settings = None

        async def execute_task(self, session_id: str, instruction: str, on_step=None, on_frame=None, on_workflow_step=None, **kwargs):
            self.last_settings = kwargs.get("settings")
            return await super().execute_task(
                session_id=session_id,
                instruction=instruction,
                on_step=on_step,
                on_frame=on_frame,
                on_workflow_step=on_workflow_step,
                **kwargs,
            )

    orchestrator = _CapturingOrchestrator()
    main.orchestrator = orchestrator

    class _ResolvedContext:
        def as_settings_fragment(self) -> dict[str, object]:
            return {
                "resolved_skill_ids": ["skill-1"],
                "skill_runtime_meta": {
                    "version_hashes": {"skill-1": "hash-1"},
                    "policy_refs": {"skill-1": "skill_status:published_hub"},
                    "resolved_at": "2026-04-06T00:00:00+00:00",
                },
            }

    async def _fake_resolve(user_uid: str | None, requested_ids: list[str]):
        assert requested_ids == ["skill-1", "skill-2"]
        return _ResolvedContext()

    monkeypatch.setattr(main, "resolve_runtime_skills", _fake_resolve)
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "config", "settings": {"enabled_skill_ids": ["skill-1", "skill-2"]}})
        ack = ws.receive_json()
        ws.send_json({"action": "navigate", "instruction": "run with resolved skills"})
        _ = ws.receive_json()
        _ = ws.receive_json()
        _ = ws.receive_json()
        _ = ws.receive_json()
        ws.send_json({"action": "stop"})

    assert ack["type"] == "step"
    assert orchestrator.last_settings is not None
    assert orchestrator.last_settings["enabled_skill_ids"] == ["skill-1", "skill-2"]
    assert orchestrator.last_settings["resolved_skill_ids"] == ["skill-1"]


def test_websocket_config_rejects_invalid_enabled_skill_ids_shape() -> None:
    """Config action should return an error when enabled_skill_ids has invalid shape."""
    main.orchestrator = _StubOrchestrator()
    client = TestClient(main.app)

    with client.websocket_connect("/ws/navigate") as ws:
        _ = ws.receive_json()
        ws.send_json({"action": "config", "settings": {"enabled_skill_ids": "not-a-list"}})
        error = ws.receive_json()
        ws.send_json({"action": "stop"})

    assert error["type"] == "error"
    assert "enabled_skill_ids must be an array of strings" in error["data"]["message"]
