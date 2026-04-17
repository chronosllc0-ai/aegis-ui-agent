"""Regression coverage for runtime telemetry counters and derived rates."""

from __future__ import annotations

from backend.runtime_telemetry import RuntimeTelemetry


def test_runtime_telemetry_tracks_channel_tool_rates_and_platform_breakdown() -> None:
    telemetry = RuntimeTelemetry()

    telemetry.record_channel_tool_result("telegram", ok=True)
    telemetry.record_channel_tool_result("telegram", ok=False)
    telemetry.record_channel_tool_result("slack", ok=True)

    snapshot = telemetry.snapshot()
    assert snapshot["channel_tool_success"] == 2
    assert snapshot["channel_tool_failure"] == 1
    assert snapshot["channel_tool_success_rate"] == 2 / 3
    assert snapshot["channel_tool_failure_rate"] == 1 / 3
    assert snapshot["channel_tool_by_platform"]["telegram"] == {"success": 1, "failure": 1}
    assert snapshot["channel_tool_by_platform"]["slack"] == {"success": 1, "failure": 0}


def test_runtime_telemetry_tracks_control_mode_changes_and_blocked_sends() -> None:
    telemetry = RuntimeTelemetry()

    telemetry.record_control_mode_change()
    telemetry.record_control_mode_change()
    telemetry.record_auto_mode_blocked_send()

    snapshot = telemetry.snapshot()
    assert snapshot["control_mode_changes"] == 2
    assert snapshot["auto_mode_blocked_sends"] == 1
