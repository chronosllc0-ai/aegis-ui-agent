"""Tests for mode normalization and policy enforcement."""

from __future__ import annotations

from backend.modes import blocked_tools_for_mode, normalize_agent_mode
from universal_navigator import _available_tools


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
