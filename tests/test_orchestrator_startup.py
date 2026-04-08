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
