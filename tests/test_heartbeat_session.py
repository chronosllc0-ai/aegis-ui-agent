from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from backend.heartbeat_session import HEARTBEAT_WORKSPACE_PATH, HeartbeatSessionScheduler, build_heartbeat_prompt


def test_build_heartbeat_prompt_contains_required_path_and_time() -> None:
    prompt = build_heartbeat_prompt(now=datetime(2026, 4, 22, 12, 30, tzinfo=timezone.utc))
    assert "Read HEARTBEAT.md if it exists" in prompt
    assert HEARTBEAT_WORKSPACE_PATH in prompt
    assert "Do not read docs/heartbeat.md" in prompt
    assert "Current time:" in prompt


def test_scheduler_skips_when_previous_run_active() -> None:
    async def _dispatch(_: str, __: str) -> None:
        return None

    scheduler = HeartbeatSessionScheduler(dispatch=_dispatch, interval_seconds=60)
    scheduler._state.running = True  # noqa: SLF001 - internal state guard validation
    asyncio.run(scheduler.run_once())
    assert scheduler._state.running is True
