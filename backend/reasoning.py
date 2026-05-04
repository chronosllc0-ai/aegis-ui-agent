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
    "xhigh": "Extra High",
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

_OPENAI_GPT5_LEVELS: tuple[ReasoningLevel, ...] = ("none", "minimal", "low", "medium", "high")
_STANDARD_EFFORT_LEVELS: tuple[ReasoningLevel, ...] = ("none", "low", "medium", "high")
_OFF_ONLY_LEVELS: tuple[ReasoningLevel, ...] = ("none",)
_DIRECT_ANTHROPIC_REASONING_PREFIXES = (
    "claude-opus-4",
    "claude-sonnet-4",
    "claude-haiku-4",
)
_OPENROUTER_QWEN_REASONING_MODELS = frozenset({"qwen/qwen3-max-thinking"})


def supported_reasoning_levels(provider: object, model: object) -> tuple[ReasoningLevel, ...]:
    """Return exact canonical effort levels accepted for a provider/model pair.

    The frontend uses the same policy for the effort dropdown, but the
    backend must also clamp because stale localStorage or older clients can
    still submit global values such as ``xhigh`` to models whose providers do
    not accept them. ``none`` is always present and means do not send a
    provider reasoning-effort knob.
    """

    provider_id = str(provider or "").strip().lower()
    model_id = str(model or "").strip().lower()

    if provider_id == "fireworks":
        # Kimi K2.5 can expose native thinking in output, but Fireworks'
        # OpenAI-compatible endpoint does not expose our global effort enum.
        return _OFF_ONLY_LEVELS

    if provider_id == "xai":
        if model_id in {"grok-3-mini", "grok-3-mini-fast"}:
            return _STANDARD_EFFORT_LEVELS
        return _OFF_ONLY_LEVELS

    if provider_id == "openai":
        if model_id.startswith("gpt-5"):
            return _OPENAI_GPT5_LEVELS
        if model_id in {"o3", "o4-mini"}:
            return _STANDARD_EFFORT_LEVELS
        return _OFF_ONLY_LEVELS

    if provider_id == "google":
        if model_id.startswith("gemini-2.5") or model_id.startswith("gemini-3"):
            return _STANDARD_EFFORT_LEVELS
        return _OFF_ONLY_LEVELS

    if provider_id == "anthropic":
        if model_id.startswith(_DIRECT_ANTHROPIC_REASONING_PREFIXES):
            return _STANDARD_EFFORT_LEVELS
        return _OFF_ONLY_LEVELS

    if provider_id in {"chronos", "openrouter"}:
        # OpenRouter/Chronos model ids include the upstream provider prefix.
        if model_id.startswith("openai/gpt-5"):
            return _OPENAI_GPT5_LEVELS
        if model_id in {"openai/o3", "openai/o4-mini"}:
            return _STANDARD_EFFORT_LEVELS
        if model_id.startswith("google/gemini-2.5") or model_id.startswith("google/gemini-3"):
            return _STANDARD_EFFORT_LEVELS
        if model_id.startswith("x-ai/grok-3-mini"):
            return _STANDARD_EFFORT_LEVELS
        if model_id.split(":", 1)[0] in _OPENROUTER_QWEN_REASONING_MODELS:
            return _STANDARD_EFFORT_LEVELS
        return _OFF_ONLY_LEVELS

    return _OFF_ONLY_LEVELS


def clamp_reasoning_level_for_model(provider: object, model: object, level: object) -> ReasoningLevel:
    """Clamp a requested effort to the provider/model-supported set."""

    requested = normalize_reasoning_level(level, fallback="medium")
    supported = supported_reasoning_levels(provider, model)
    if requested in supported:
        return requested
    if requested == "xhigh" and "high" in supported:
        return "high"
    if requested == "minimal" and "low" in supported:
        return "low"
    if "medium" in supported:
        return "medium"
    if "low" in supported:
        return "low"
    return "none"


def apply_reasoning_level_for_model(
    settings: dict[str, Any],
    *,
    provider: object,
    model: object,
    level: object,
) -> ReasoningLevel:
    """Apply reasoning settings after provider/model-specific clamping."""

    return apply_reasoning_level(settings, clamp_reasoning_level_for_model(provider, model, level))


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
