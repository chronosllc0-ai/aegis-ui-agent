"""Shared capability matrix + graceful fallback helpers for channel connectors."""

from __future__ import annotations

from typing import Any

CAPABILITY_MATRIX: dict[str, dict[str, str]] = {
    "telegram": {
        "send_text": "supported",
        "edit_message": "supported",
        "delete_message": "supported",
        "react": "supported",
        "send_file": "supported",
        "interactive_actions": "supported",
        "command_controls": "supported",
    },
    "slack": {
        "send_text": "supported",
        "edit_message": "supported",
        "delete_message": "supported",
        "react": "supported",
        "send_file": "supported",
        "interactive_actions": "supported",
        "command_controls": "supported",
    },
    "discord": {
        "send_text": "supported",
        "edit_message": "supported",
        "delete_message": "supported",
        "react": "supported",
        "send_file": "supported",
        "interactive_actions": "supported",
        "command_controls": "supported",
    },
}

TOOL_CAPABILITY_MAP: dict[str, str] = {
    "telegram_send_message": "send_text",
    "slack_send_message": "send_text",
    "discord_send_message": "send_text",
    "telegram_edit_message": "edit_message",
    "slack_edit_message": "edit_message",
    "discord_edit_message": "edit_message",
    "telegram_delete_message": "delete_message",
    "slack_delete_message": "delete_message",
    "discord_delete_message": "delete_message",
    "telegram_react": "react",
    "slack_react": "react",
    "discord_react": "react",
    "telegram_send_file": "send_file",
    "slack_send_file": "send_file",
    "discord_send_file": "send_file",
    "telegram_send_interactive": "interactive_actions",
    "slack_send_interactive": "interactive_actions",
    "discord_send_interactive": "interactive_actions",
    "slack_handle_event": "command_controls",
    "discord_handle_event": "command_controls",
}


def resolve_capability_status(platform: str, tool_name: str) -> tuple[str, str]:
    """Resolve capability state (`supported|partial|unsupported`) for a tool."""
    capability = TOOL_CAPABILITY_MAP.get(tool_name, "")
    platform_caps = CAPABILITY_MATRIX.get(platform, {})
    if not capability:
        return ("unsupported", "")
    return (platform_caps.get(capability, "unsupported"), capability)


def unsupported_action_fallback(platform: str, tool_name: str) -> dict[str, Any]:
    """Build normalized graceful fallback payload for unsupported actions."""
    status, capability = resolve_capability_status(platform, tool_name)
    return {
        "ok": False,
        "tool": tool_name,
        "fallback": True,
        "capability": capability or "unknown",
        "error": f"{tool_name} is {status} on {platform}; returning graceful fallback.",
    }
