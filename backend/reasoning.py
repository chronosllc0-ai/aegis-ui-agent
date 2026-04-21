"""Canonical reasoning-effort normalization + runtime setting adapters."""

from __future__ import annotations

from typing import Any, Literal

ReasoningLevel = Literal["none", "minimal", "low", "medium", "high", "xhigh"]

CANONICAL_REASONING_LEVELS: tuple[ReasoningLevel, ...] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)

_REASONING_LABELS: dict[ReasoningLevel, str] = {
    "none": "None",
    "minimal": "Minimal",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "xhigh": "XHigh",
}

_REASONING_ALIASES: dict[str, ReasoningLevel] = {
    "off": "none",
    "on": "medium",
    "true": "medium",
    "1": "medium",
    "false": "none",
    "0": "none",
    "extended": "xhigh",
    "adaptive": "medium",
    "x-high": "xhigh",
    "extra_high": "xhigh",
}


def normalize_reasoning_level(value: object, *, fallback: ReasoningLevel | None = None) -> ReasoningLevel:
    """Normalize user-provided reasoning values to strict canonical level tokens."""

    normalized = str(value or "").strip().lower()
    if normalized in CANONICAL_REASONING_LEVELS:
        return normalized  # type: ignore[return-value]
    if normalized in _REASONING_ALIASES:
        return _REASONING_ALIASES[normalized]
    if fallback is not None:
        return fallback
    allowed = ", ".join(CANONICAL_REASONING_LEVELS)
    raise ValueError(f"Invalid reasoning level {value!r}. Expected one of: {allowed}")


def reasoning_level_label(level: object) -> str:
    """Return title-cased display label for reasoning effort values."""

    canonical = normalize_reasoning_level(level, fallback="medium")
    return _REASONING_LABELS[canonical]


def apply_reasoning_level(settings: dict[str, Any], level: object) -> ReasoningLevel:
    """Apply canonical reasoning level to runtime settings using compatibility fields."""

    canonical = normalize_reasoning_level(level, fallback="medium")
    enabled = canonical != "none"
    settings["reasoning_enabled"] = enabled
    settings["enable_reasoning"] = enabled
    settings["reasoning_effort"] = canonical
    if not enabled:
        settings["stream_reasoning"] = False
    return canonical


def runtime_reasoning_level(settings: dict[str, Any]) -> ReasoningLevel:
    """Resolve canonical reasoning level from runtime settings with stale-value fallback."""

    effort_raw = settings.get("reasoning_effort")
    effort = normalize_reasoning_level(effort_raw, fallback="medium")
    enabled_raw = settings.get("reasoning_enabled")
    if enabled_raw is None:
        enabled_raw = settings.get("enable_reasoning")
    enabled = bool(enabled_raw)
    if not enabled:
        return "none"
    return effort if effort != "none" else "medium"


def runtime_reasoning_status(settings: dict[str, Any]) -> dict[str, Any]:
    """Return canonical reasoning status payload for status surfaces."""

    level = runtime_reasoning_level(settings)
    enabled = level != "none"
    return {
        "level": level,
        "label": reasoning_level_label(level),
        "enabled": enabled,
        "stream_reasoning": bool(settings.get("stream_reasoning", False)),
    }
