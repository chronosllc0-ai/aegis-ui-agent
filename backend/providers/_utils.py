"""Shared provider utility helpers."""

from __future__ import annotations


def normalize_reasoning_effort(effort: str) -> str:
    """Normalize UI effort labels to provider-supported low/medium/high values."""
    normalized = (effort or "medium").strip().lower()
    if normalized == "extended":
        return "high"
    if normalized == "adaptive":
        return "medium"
    return normalized if normalized in {"low", "medium", "high"} else "medium"

