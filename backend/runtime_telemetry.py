"""In-memory runtime telemetry counters for rollout safety and observability."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RuntimeTelemetry:
    """Collect lightweight process-local counters for runtime/channel controls."""

    control_mode_changes: int = 0
    auto_mode_blocked_sends: int = 0
    channel_tool_success: int = 0
    channel_tool_failure: int = 0
    channel_tool_by_platform: dict[str, dict[str, int]] = field(default_factory=dict)

    def record_control_mode_change(self) -> None:
        """Increment mode-change metric for interactive runtime controls."""
        self.control_mode_changes += 1

    def record_auto_mode_blocked_send(self) -> None:
        """Increment blocked-send metric when auto-mode hides/disables send controls."""
        self.auto_mode_blocked_sends += 1

    def record_channel_tool_result(self, platform: str, *, ok: bool) -> None:
        """Track channel tool outcome counters globally and per-platform."""
        platform_key = str(platform or "unknown").strip().lower() or "unknown"
        bucket = self.channel_tool_by_platform.setdefault(platform_key, {"success": 0, "failure": 0})
        if ok:
            self.channel_tool_success += 1
            bucket["success"] = int(bucket.get("success", 0)) + 1
        else:
            self.channel_tool_failure += 1
            bucket["failure"] = int(bucket.get("failure", 0)) + 1

    def snapshot(self) -> dict[str, Any]:
        """Return telemetry metrics and derived success/failure rates."""
        total = self.channel_tool_success + self.channel_tool_failure
        success_rate = float(self.channel_tool_success / total) if total else 0.0
        failure_rate = float(self.channel_tool_failure / total) if total else 0.0
        return {
            "control_mode_changes": self.control_mode_changes,
            "auto_mode_blocked_sends": self.auto_mode_blocked_sends,
            "channel_tool_success": self.channel_tool_success,
            "channel_tool_failure": self.channel_tool_failure,
            "channel_tool_success_rate": success_rate,
            "channel_tool_failure_rate": failure_rate,
            "channel_tool_by_platform": {
                key: {"success": int(value.get("success", 0)), "failure": int(value.get("failure", 0))}
                for key, value in sorted(self.channel_tool_by_platform.items())
            },
        }
