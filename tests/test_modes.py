"""Tests for mode normalization and policy enforcement."""

from __future__ import annotations

from types import SimpleNamespace

from backend.modes import blocked_tools_for_mode, normalize_agent_mode
from universal_navigator import UniversalToolExecutor, _available_tools


def test_normalize_agent_mode_falls_back_to_orchestrator() -> None:
    """Unknown mode values should resolve to orchestrator."""
    assert normalize_agent_mode("unknown") == "orchestrator"


def test_read_only_modes_block_execution_tools() -> None:
    """Planner/architect/research modes should block mutating execution tools."""
    blocked = blocked_tools_for_mode("planner")
    assert "exec_shell" in blocked
    assert "spawn_subagent" in blocked


def test_orchestrator_mode_blocks_subagent_spawn() -> None:
    """Orchestrator mode should not directly spawn subagents."""
    blocked = blocked_tools_for_mode("orchestrator")
    assert "spawn_subagent" in blocked


def test_available_tools_respect_mode_blocks() -> None:
    """Tool manifest should remove spawn_subagent outside code mode."""
    tools = _available_tools({"agent_mode": "planner"}, is_subagent=False)
    tool_names = {tool["name"] for tool in tools}
    assert "spawn_subagent" not in tool_names

    code_tools = _available_tools({"agent_mode": "code"}, is_subagent=False)
    code_tool_names = {tool["name"] for tool in code_tools}
    assert "spawn_subagent" in code_tool_names


def test_skill_deny_blocks_even_when_mode_allows() -> None:
    """Skill denylist should block tools even in permissive mode settings."""
    tools = _available_tools({"agent_mode": "code", "skill_deny_tools": ["web_search"]}, is_subagent=False)
    tool_names = {tool["name"] for tool in tools}
    assert "web_search" not in tool_names


def test_skill_allow_intersection_narrows_available_tools() -> None:
    """Skill allowlist should narrow manifest to explicit allowed tools."""
    tools = _available_tools({"agent_mode": "code", "skill_allow_tools": ["read_file", "list_files"]}, is_subagent=False)
    tool_names = {tool["name"] for tool in tools}
    assert "read_file" in tool_names
    assert "list_files" in tool_names
    assert "web_search" not in tool_names


def test_skill_deny_overrides_skill_allow() -> None:
    """Skill denylist should take precedence over overlapping allowlist entries."""
    tools = _available_tools(
        {"agent_mode": "code", "skill_allow_tools": ["read_file", "web_search"], "skill_deny_tools": ["web_search"]},
        is_subagent=False,
    )
    tool_names = {tool["name"] for tool in tools}
    assert "read_file" in tool_names
    assert "web_search" not in tool_names


def test_tool_unavailable_reason_prioritizes_skill_policy() -> None:
    """Denied tools should expose skill policy as the unavailability source."""
    executor = UniversalToolExecutor(
        SimpleNamespace(),
        session_id="sess-1",
        settings={"agent_mode": "code", "skill_deny_tools": ["web_search"]},
    )
    reason = executor._tool_unavailable_reason("web_search")
    assert reason is not None
    assert "skill policy denylist" in reason


def test_no_skill_policy_keeps_default_manifest_behavior() -> None:
    """Sessions without skill policy should match baseline mode-gated tool availability."""
    baseline = {tool["name"] for tool in _available_tools({"agent_mode": "code"}, is_subagent=False)}
    no_skill = {tool["name"] for tool in _available_tools({"agent_mode": "code", "enabled_skill_ids": []}, is_subagent=False)}
    assert no_skill == baseline
