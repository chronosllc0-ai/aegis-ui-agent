"""Tests for screenshot analyzer parsing."""

from __future__ import annotations

from analyzer import ScreenshotAnalyzer


def test_parse_response_handles_json_fence() -> None:
    """Parser should accept fenced JSON output."""
    raw = """```json\n{\"page_type\":\"search\",\"elements\":[{\"description\":\"Search box\",\"element_type\":\"input\",\"x_pct\":50,\"y_pct\":30,\"state\":\"empty\",\"text\":\"\"}],\"current_state\":\"ready\",\"navigation_context\":\"google\"}\n```"""
    parsed = ScreenshotAnalyzer._parse_response(raw)
    assert parsed["page_type"] == "search"
    assert len(parsed["elements"]) == 1
    assert parsed["elements"][0]["element_type"] == "input"
