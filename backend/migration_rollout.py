"""Session migration rollout controls and feature-flag helpers."""

from __future__ import annotations

from config import settings


def feature_flags_snapshot() -> dict[str, bool]:
    """Return externally visible migration feature flags."""
    return {
        "workspace_prompt_mode": bool(settings.FEATURE_FLAG_WORKSPACE_PROMPT_MODE),
        "sessions_v2": bool(settings.FEATURE_FLAG_SESSIONS_V2),
        "observability_event_log": bool(settings.FEATURE_FLAG_OBSERVABILITY_EVENT_LOG),
    }


def sessions_v2_enabled() -> bool:
    """Return whether reads should prefer the sessions-v2 store."""
    return bool(settings.FEATURE_FLAG_SESSIONS_V2) and not bool(settings.SESSIONS_V2_LEGACY_FALLBACK)


def sessions_dual_write_enabled() -> bool:
    """Return whether writes should be mirrored to legacy conversation storage."""
    return sessions_v2_enabled() and bool(settings.SESSIONS_V2_DUAL_WRITE)


def legacy_conversation_mode_enabled() -> bool:
    """Return whether rollback forces legacy conversation behavior."""
    return bool(settings.SESSIONS_V2_LEGACY_FALLBACK) or not bool(settings.FEATURE_FLAG_SESSIONS_V2)
