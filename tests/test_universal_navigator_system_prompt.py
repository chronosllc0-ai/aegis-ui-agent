"""Regression tests for universal navigator system prompt composition."""

from __future__ import annotations

import asyncio

import universal_navigator
from backend.providers.base import StreamChunk


def test_build_system_prompt_uses_global_and_optional_user_instructions(monkeypatch) -> None:
    """System prompt should always include global instruction and optionally append user instruction."""
    monkeypatch.setattr(universal_navigator, "_session_factory", None, raising=False)
    monkeypatch.setattr(
        universal_navigator._app_settings,
        "AEGIS_GLOBAL_SYSTEM_INSTRUCTION",
        "Global admin instruction",
    )

    prompt_with_user = asyncio.run(
        universal_navigator._build_system_prompt(
            session_id="prompt-test-session",
            settings={"system_instruction": "User override guidance"},
            is_subagent=False,
        )
    )
    assert "Global operator instructions" in prompt_with_user
    assert "Global admin instruction" in prompt_with_user
    assert "Runtime instructions from the user" in prompt_with_user
    assert "User override guidance" in prompt_with_user

    prompt_without_user = asyncio.run(
        universal_navigator._build_system_prompt(
            session_id="prompt-test-session",
            settings={},
            is_subagent=False,
        )
    )
    assert "Global operator instructions" in prompt_without_user
    assert "Global admin instruction" in prompt_without_user
    assert "Runtime instructions from the user" not in prompt_without_user


def test_extended_reasoning_effort_maps_to_higher_budget() -> None:
    """Extended effort should propagate a larger reasoning budget to provider.stream."""

    class _StubProvider:
        def __init__(self) -> None:
            self.last_kwargs: dict[str, object] = {}

        async def stream(self, _messages, **kwargs):  # type: ignore[no-untyped-def]
            self.last_kwargs = kwargs
            yield StreamChunk(delta='{"tool":"done","summary":"ok"}')

    provider = _StubProvider()
    result = asyncio.run(
        universal_navigator.run_universal_navigation(
            provider=provider,  # type: ignore[arg-type]
            model="claude-sonnet-4-20250514",
            executor=object(),
            session_id="budget-test-session",
            instruction="Sanity check",
            enable_reasoning=True,
            reasoning_effort="extended",
        )
    )
    assert result["status"] == "completed"
    assert provider.last_kwargs.get("reasoning_effort") == "extended"
    assert provider.last_kwargs.get("reasoning_budget") == 24000
