"""Feature flags for staged rollout of advanced channel tooling."""

from __future__ import annotations

from config import settings

ADVANCED_CHANNEL_TOOLS: dict[str, set[str]] = {
    "telegram": {
        "telegram_send_poll",
        "telegram_topic_create",
        "telegram_topic_edit",
        "telegram_send_interactive",
    },
    "slack": {
        "slack_send_interactive",
    },
    "discord": {
        "discord_send_interactive",
    },
}


def is_advanced_tool_enabled(platform: str) -> bool:
    """Return whether advanced tooling is enabled for a channel platform."""
    normalized_platform = str(platform or "").strip().lower()
    if normalized_platform == "telegram":
        return bool(settings.CHANNEL_TOOLS_TELEGRAM_ADVANCED_ENABLED)
    if normalized_platform == "slack":
        return bool(settings.CHANNEL_TOOLS_SLACK_ADVANCED_ENABLED)
    if normalized_platform == "discord":
        return bool(settings.CHANNEL_TOOLS_DISCORD_ADVANCED_ENABLED)
    return True


def advanced_tool_blocked(platform: str, tool_name: str) -> bool:
    """Return True when tool is advanced and currently disabled by rollout flag."""
    normalized_platform = str(platform or "").strip().lower()
    if tool_name not in ADVANCED_CHANNEL_TOOLS.get(normalized_platform, set()):
        return False
    return not is_advanced_tool_enabled(normalized_platform)
