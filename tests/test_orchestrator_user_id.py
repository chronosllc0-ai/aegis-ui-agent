"""Regression tests for orchestrator session user id isolation."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import orchestrator


class _FakeRunner:
    last_kwargs: dict[str, str] | None = None

    def __init__(self, agent, app_name, session_service) -> None:  # noqa: ANN001
        self.agent = agent

    async def run_async(self, user_id: str, session_id: str, new_message: str):
        _FakeRunner.last_kwargs = {"user_id": user_id, "session_id": session_id, "new_message": new_message}
        if False:
            yield None
        return


def test_execute_task_uses_session_id_for_user_id(monkeypatch) -> None:
    async def run() -> None:
        orch = orchestrator.AgentOrchestrator()
        orch.agent = object()

        async def fake_resolve(settings):  # noqa: ANN001
            return object(), orch.default_model_name

        calls: dict[str, str] = {}

        async def fake_create_session(app_name: str, user_id: str, session_id: str) -> None:
            calls["user_id"] = user_id
            calls["session_id"] = session_id

        orch._resolve_session_agent = fake_resolve  # type: ignore[assignment]
        orch.session_service = SimpleNamespace(create_session=fake_create_session)

        monkeypatch.setattr(orchestrator, "Runner", _FakeRunner)

        result = await orch.execute_task(session_id="session-123", instruction="hello")
        assert result["status"] == "completed"
        assert calls["user_id"] == "session-123"
        assert _FakeRunner.last_kwargs is not None
        assert _FakeRunner.last_kwargs["user_id"] == "session-123"

    asyncio.run(run())
