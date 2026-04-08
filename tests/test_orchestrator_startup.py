"""Regression tests for provider-agnostic orchestrator startup stability."""

from __future__ import annotations

import asyncio

import orchestrator


def test_orchestrator_init_without_gemini_key_does_not_raise(monkeypatch) -> None:
    """Orchestrator construction must not require Gemini credentials upfront."""
    monkeypatch.setattr(orchestrator.settings, "GEMINI_API_KEY", "")
    orch = orchestrator.AgentOrchestrator()
    assert orch.client is None
    assert orch.analyzer is None
    assert orch.navigator is None


def test_non_gemini_execute_task_fails_gracefully_without_provider_key(monkeypatch) -> None:
    """Non-Gemini requests should return a clean key error instead of crashing startup."""
    monkeypatch.setattr(orchestrator.settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(orchestrator.settings, "OPENAI_API_KEY", "")

    async def _run() -> None:
        orch = orchestrator.AgentOrchestrator()
        result = await orch.execute_task(
            session_id="session-no-key",
            instruction="Open example.com",
            settings={"provider": "openai", "model": "gpt-4o-mini"},
        )
        assert result["status"] == "failed"
        assert "No API key found for provider 'openai'" in str(result.get("error", ""))

    asyncio.run(_run())


def test_gemini_path_uses_module_settings_not_session_dict(monkeypatch) -> None:
    """Gemini key validation must reference config settings, not per-session payload dicts."""
    monkeypatch.setattr(orchestrator.settings_module, "GEMINI_API_KEY", "test-gemini-key")

    class _FakeRunner:
        def __init__(self, agent, app_name, session_service) -> None:  # noqa: ANN001
            self._agent = agent
            self._app_name = app_name
            self._session_service = session_service

        async def run_async(self, user_id: str, session_id: str, new_message: str):  # noqa: ANN001
            if False:
                yield user_id, session_id, new_message

    async def _run() -> None:
        orch = orchestrator.AgentOrchestrator()
        orch.agent = object()  # skip initialize path

        async def _noop_apply(_: dict[str, object] | None) -> None:
            return None

        async def _resolve(_: dict[str, object] | None):
            return object(), "gemini-2.5-pro"

        monkeypatch.setattr(orch, "_apply_session_settings", _noop_apply)
        monkeypatch.setattr(orch, "_resolve_session_agent", _resolve)
        monkeypatch.setattr(orchestrator, "Runner", _FakeRunner)

        result = await orch.execute_task(
            session_id="session-gemini",
            instruction="hello",
            settings={"provider": "google", "model": "gemini-2.5-pro"},
        )

        assert result["status"] == "completed"

    asyncio.run(_run())
