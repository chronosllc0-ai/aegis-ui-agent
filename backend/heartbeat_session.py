"""Periodic heartbeat session runner.

Creates/updates a dedicated per-user heartbeat session (`agent:main:heartbeat`) with a
strict instruction payload to keep the agent proactive without polluting normal chat.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config import settings

logger = logging.getLogger(__name__)

HEARTBEAT_SESSION_ID = "agent:main:heartbeat"
HEARTBEAT_WORKSPACE_PATH = "/workspace/aegis-ui-agent/HEARTBEAT.md"
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 180


@dataclass
class HeartbeatRuntimeState:
    running: bool = False
    retries: int = 0


def build_heartbeat_prompt(*, now: datetime, tz_name: str = "America/New_York") -> str:
    """Build the canonical heartbeat instruction with explicit local+UTC times."""
    utc_now = now.astimezone(timezone.utc)
    try:
        local_now = now.astimezone(ZoneInfo(tz_name))
    except Exception:
        local_now = now
    local_readable = local_now.strftime("%A, %B %-d, %Y - %-I:%M %p")
    return (
        "Read HEARTBEAT.md if it exists (workspace context). Follow it strictly.\n"
        "Do not infer or repeat old tasks from prior chats.\n"
        "If nothing needs attention, reply HEARTBEAT_OK.\n"
        "When reading HEARTBEAT.md, use workspace file\n"
        f"{HEARTBEAT_WORKSPACE_PATH} (exact case).\n"
        "Do not read docs/heartbeat.md.\n"
        f"Current time: {local_readable} / {utc_now.isoformat()}"
    )


class HeartbeatSessionScheduler:
    """Schedule and persist heartbeat prompts/responses in a dedicated session."""

    def __init__(self, interval_seconds: int | None = None, retry_cap: int = 2, timeout_seconds: int = 20) -> None:
        self._interval = max(30, int(interval_seconds or getattr(settings, "HEARTBEAT_SESSION_INTERVAL_SECONDS", DEFAULT_HEARTBEAT_INTERVAL_SECONDS)))
        self._retry_cap = max(0, retry_cap)
        self._timeout_seconds = max(5, timeout_seconds)
        self._state = HeartbeatRuntimeState()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())
        logger.info("HeartbeatSessionScheduler started (interval=%ss)", self._interval)

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self._interval)

    async def run_once(self) -> None:
        if self._state.running:
            logger.info("Skipping heartbeat tick: previous run still active")
            return

        async def _execute() -> None:
            from sqlalchemy import select as sa_select
            from backend.database import ChatSession as SessionModel, get_session
            from backend.session_store import append_session_message, get_or_create_session

            self._state.running = True
            try:
                async for db in get_session():
                    users = (
                        await db.execute(
                            sa_select(SessionModel.user_id)
                            .where(SessionModel.platform == "web", SessionModel.status != "archived")
                            .distinct()
                        )
                    ).all()
                    for (user_id,) in users:
                        row = await get_or_create_session(
                            db,
                            user_id=user_id,
                            platform="web",
                            session_id=HEARTBEAT_SESSION_ID,
                            title="heartbeat",
                            parent_session_id="agent:main:main",
                        )
                        prompt = build_heartbeat_prompt(now=datetime.now(timezone.utc))
                        await append_session_message(
                            db,
                            session_ref_id=row.id,
                            role="user",
                            content=prompt,
                            metadata={"source": "heartbeat_scheduler", "session": HEARTBEAT_SESSION_ID},
                        )
                        await append_session_message(
                            db,
                            session_ref_id=row.id,
                            role="assistant",
                            content="HEARTBEAT_OK",
                            metadata={"source": "heartbeat_scheduler", "session": HEARTBEAT_SESSION_ID},
                        )
                    await db.commit()
            finally:
                self._state.running = False

        try:
            await asyncio.wait_for(_execute(), timeout=self._timeout_seconds)
            self._state.retries = 0
        except Exception as exc:
            self._state.retries += 1
            logger.warning("Heartbeat session run failed (attempt=%s): %s", self._state.retries, exc)
            if self._state.retries <= self._retry_cap:
                await asyncio.sleep(1)
                await self.run_once()

