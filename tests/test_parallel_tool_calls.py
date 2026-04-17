"""Tests for parallel tool-call parsing and safety gating."""

from __future__ import annotations

from universal_navigator import TOOL_INDEX, _can_run_tool_calls_in_parallel, _parse_tool_calls


def test_parse_tool_calls_single_object() -> None:
    """Single tool call object should parse as one-entry list."""
    parsed = _parse_tool_calls('{"tool":"web_search","query":"aegis"}')
    assert len(parsed) == 1
    assert parsed[0]["tool"] == "web_search"


def test_parse_tool_calls_batch_object() -> None:
    """tool_calls array should be extracted from wrapper object."""
    payload = '{"tool_calls":[{"tool":"web_search","query":"one"},{"tool":"extract_page","url":"https://example.com"}]}'
    parsed = _parse_tool_calls(payload)
    assert [entry["tool"] for entry in parsed] == ["web_search", "extract_page"]


def test_parallel_safety_allows_only_safe_tools() -> None:
    """Only explicitly allowlisted tools should run concurrently."""
    safe_calls = [{"tool": "web_search", "query": "one"}, {"tool": "extract_page", "url": "https://example.com"}]
    assert _can_run_tool_calls_in_parallel(safe_calls)

    unsafe_calls = [{"tool": "web_search", "query": "one"}, {"tool": "exec_shell", "command": "echo hi"}]
    assert not _can_run_tool_calls_in_parallel(unsafe_calls)


def test_tool_manifest_includes_steer_subagent() -> None:
    """steer_subagent should be available as a first-class tool."""
    assert "steer_subagent" in TOOL_INDEX
