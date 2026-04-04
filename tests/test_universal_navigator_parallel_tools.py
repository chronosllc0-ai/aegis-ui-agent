"""Tests for batched tool-call orchestration in universal_navigator."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from backend.providers.base import BaseProvider, ChatMessage, ChatResponse, StreamChunk
import universal_navigator


class _ScriptedProvider(BaseProvider):
    provider_name = "scripted"

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.stream_messages: list[list[ChatMessage]] = []

    async def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:  # pragma: no cover
        return ChatResponse(content="", model="scripted", provider=self.provider_name)

    async def stream(self, messages: list[ChatMessage], **kwargs: Any):
        self.stream_messages.append(list(messages))
        yield StreamChunk(delta=self._replies.pop(0))


async def _run_navigation(provider: BaseProvider, **kwargs: Any) -> dict[str, Any]:
    async def _fake_load_runtime_skills(**_inner: Any):
        return "", [], []

    original = universal_navigator._load_runtime_skills
    universal_navigator._load_runtime_skills = _fake_load_runtime_skills
    try:
        return await universal_navigator.run_universal_navigation(
            provider=provider,
            model="fake-model",
            executor=SimpleNamespace(),
            session_id="task-123",
            instruction="Do work",
            **kwargs,
        )
    finally:
        universal_navigator._load_runtime_skills = original


def test_accepts_valid_tool_calls_batch_of_three(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        provider = _ScriptedProvider([
            '{"tool_calls":[{"tool":"wait","seconds":0},{"tool":"wait","seconds":0},{"tool":"wait","seconds":0}]}',
            '{"tool":"done","summary":"ok"}',
        ])
    
        calls: list[dict[str, Any]] = []
    
        async def fake_run(self: universal_navigator.UniversalToolExecutor, tool_call: dict[str, Any], *, skip_policy_checks: bool = False):
            calls.append(tool_call)
            return f"ran:{tool_call['tool']}", None
    
        monkeypatch.setattr(universal_navigator.UniversalToolExecutor, "run", fake_run)
        result = await _run_navigation(provider)
    
        assert result["status"] == "completed"
        assert len(calls) == 3
        follow_up = provider.stream_messages[1][-1].content
        assert "Tool results:" in follow_up
    
    

    asyncio.run(_run())
def test_rejects_batch_over_three_with_safe_error() -> None:
    async def _run() -> None:
        provider = _ScriptedProvider([
            '{"tool_calls":[{"tool":"wait"},{"tool":"wait"},{"tool":"wait"},{"tool":"wait"}]}',
            '{"tool":"done","summary":"halted"}',
        ])
    
        result = await _run_navigation(provider)
    
        assert result["status"] == "completed"
        assert any("malformed tool_calls payload" in step["content"].lower() for step in result["steps"])
    
    

    asyncio.run(_run())
def test_preserves_result_ordering_with_async_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        provider = _ScriptedProvider([
            '{"tool_calls":[{"tool":"wait","seconds":0.03},{"tool":"wait","seconds":0.01},{"tool":"wait","seconds":0.02}]}',
            '{"tool":"done","summary":"ordered"}',
        ])
    
        async def fake_run(self: universal_navigator.UniversalToolExecutor, tool_call: dict[str, Any], *, skip_policy_checks: bool = False):
            await asyncio.sleep(float(tool_call.get("seconds", 0)))
            return f"slept:{tool_call['seconds']}", None
    
        monkeypatch.setattr(universal_navigator.UniversalToolExecutor, "run", fake_run)
        await _run_navigation(provider)
    
        follow_up = provider.stream_messages[1][-1].content
        assert "1) [wait] ok: slept:0.03" in follow_up
        assert "2) [wait] ok: slept:0.01" in follow_up
        assert "3) [wait] ok: slept:0.02" in follow_up
    
    

    asyncio.run(_run())
def test_mixed_pass_fail_returns_consolidated_message(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        provider = _ScriptedProvider([
            '{"tool_calls":[{"tool":"wait"},{"tool":"read_file","path":"missing.txt"}]}',
            '{"tool":"done","summary":"mixed"}',
        ])
    
        async def fake_run(self: universal_navigator.UniversalToolExecutor, tool_call: dict[str, Any], *, skip_policy_checks: bool = False):
            if tool_call["tool"] == "read_file":
                return "read_file error: missing", None
            return "ok", None
    
        monkeypatch.setattr(universal_navigator.UniversalToolExecutor, "run", fake_run)
        await _run_navigation(provider)
    
        follow_up = provider.stream_messages[1][-1].content
        assert "1) [wait] ok: ok" in follow_up
        assert "2) [read_file] error: read_file error: missing" in follow_up
    
    

    asyncio.run(_run())
def test_malformed_batch_falls_back_to_legacy_single_call(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        provider = _ScriptedProvider([
            '{"tool_calls":"bad","tool":"wait","seconds":0}',
            '{"tool":"done","summary":"fallback"}',
        ])
    
        seen: list[str] = []
    
        async def fake_run(self: universal_navigator.UniversalToolExecutor, tool_call: dict[str, Any], *, skip_policy_checks: bool = False):
            seen.append(tool_call["tool"])
            return "ok", None
    
        monkeypatch.setattr(universal_navigator.UniversalToolExecutor, "run", fake_run)
        await _run_navigation(provider)
    
        assert seen == ["wait"]
    
    

    asyncio.run(_run())
def test_high_risk_tool_in_batch_still_triggers_confirmation_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        provider = _ScriptedProvider([
            '{"tool_calls":[{"tool":"exec_shell","command":"echo nope"},{"tool":"wait","seconds":0}]}',
            '{"tool":"done","summary":"gated"}',
        ])
    
        prompts: list[str] = []
    
        async def reject_prompt(question: str, options: list[str]) -> str:
            prompts.append(question)
            return "Reject"
    
        async def fake_run(self: universal_navigator.UniversalToolExecutor, tool_call: dict[str, Any], *, skip_policy_checks: bool = False):
            return "ok", None
    
        monkeypatch.setattr(universal_navigator.UniversalToolExecutor, "run", fake_run)
        await _run_navigation(
            provider,
            settings={"tool_permissions": {"exec_shell": "confirm"}},
            on_user_input=reject_prompt,
        )
    
        follow_up = provider.stream_messages[1][-1].content
        assert any("Allow Aegis to run exec_shell?" in prompt for prompt in prompts)
        assert "[exec_shell] error: User declined tool 'exec_shell'" in follow_up
        assert "[wait] ok: ok" in follow_up
    
    

    asyncio.run(_run())
def test_integration_batch_emits_events_and_single_followup(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        provider = _ScriptedProvider([
            '{"tool_calls":[{"tool":"wait","seconds":0},{"tool":"wait","seconds":0}]}',
            '{"tool":"done","summary":"done"}',
        ])
    
        async def fake_run(self: universal_navigator.UniversalToolExecutor, tool_call: dict[str, Any], *, skip_policy_checks: bool = False):
            return "ok", None
    
        events: list[dict[str, Any]] = []

        async def capture_event(event: dict[str, Any]) -> None:
            events.append(event)

        monkeypatch.setattr(universal_navigator.UniversalToolExecutor, "run", fake_run)
        await _run_navigation(provider, on_workflow_step=capture_event)
    
        event_types = [event.get("type") for event in events]
        assert "batch_tool_start" in event_types
        assert "batch_tool_result" in event_types
        assert "batch_tool_complete" in event_types
        assert provider.stream_messages[1][-1].content.count("Tool results:") == 1
    
    

    asyncio.run(_run())
def test_integration_subagent_allowlist_enforced_in_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        provider = _ScriptedProvider([
            '{"tool_calls":[{"tool":"read_file","path":"README.md"},{"tool":"wait","seconds":0}]}',
            '{"tool":"done","summary":"done"}',
        ])
    
        async def fake_run(self: universal_navigator.UniversalToolExecutor, tool_call: dict[str, Any], *, skip_policy_checks: bool = False):
            return "ok", None
    
        monkeypatch.setattr(universal_navigator.UniversalToolExecutor, "run", fake_run)
        await _run_navigation(provider, is_subagent=True)
    
        follow_up = provider.stream_messages[1][-1].content
        assert "[read_file] error: Tool 'read_file' is not available to sub-agents." in follow_up
        assert "[wait] ok: ok" in follow_up

    asyncio.run(_run())
