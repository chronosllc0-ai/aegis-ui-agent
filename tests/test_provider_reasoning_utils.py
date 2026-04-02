"""Regression tests for shared provider reasoning-effort normalization."""

from backend.providers._utils import normalize_reasoning_effort


def test_normalize_reasoning_effort_maps_extended_and_adaptive() -> None:
    assert normalize_reasoning_effort("extended") == "high"
    assert normalize_reasoning_effort("adaptive") == "medium"


def test_normalize_reasoning_effort_defaults_safely() -> None:
    assert normalize_reasoning_effort("medium") == "medium"
    assert normalize_reasoning_effort("HIGH") == "high"
    assert normalize_reasoning_effort("") == "medium"
    assert normalize_reasoning_effort("invalid") == "medium"

