"""Periodic heartbeat session runner.

Creates/updates a dedicated per-user heartbeat session (`agent:main:heartbeat`) with a
strict instruction payload to keep the agent proactive without polluting normal chat.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Awaitable, Callable
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
    enabled: bool = True
    last_run_at_utc: str | None = None
    next_run_at_utc: str | None = None
    last_result: str = "never_run"


# Dispatch hook signature: ``(user_id, session_id, prompt)``. The
# scheduler iterates per-user, so user_id is always known and is the
# only correct way to route the prompt to the right always-on
# supervisor. Earlier versions of this signature dropped ``user_id``
# and the dispatch hook tried to reverse it via the in-memory
# ``_session_runtimes`` keyed by ws_session_id — that lookup never
# matched the shared ``agent:main:heartbeat`` session_id, which is
# why heartbeat dispatch silently became a no-op. Adding user_id
# here is what unblocks the always-on routing path.
HeartbeatDispatcher = Callable[[str, str, str], Awaitable[None]]


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

    def __init__(
        self,
        *,
        dispatch: HeartbeatDispatcher,
        interval_seconds: int | None = None,
        retry_cap: int = 2,
        timeout_seconds: int = 20,
    ) -> None:
        self._dispatch = dispatch
        self._interval = max(30, int(interval_seconds or getattr(settings, "HEARTBEAT_SESSION_INTERVAL_SECONDS", DEFAULT_HEARTBEAT_INTERVAL_SECONDS)))
        self._retry_cap = max(0, retry_cap)
        self._timeout_seconds = max(5, timeout_seconds)
        self._state = HeartbeatRuntimeState()
        self._task: asyncio.Task[None] | None = None
        self._state.enabled = bool(getattr(settings, "HEARTBEAT_SESSION_ENABLED", True))

    def start(self) -> None:
        if not self._state.enabled:
            logger.info("HeartbeatSessionScheduler is disabled by configuration")
            self._state.last_result = "disabled"
            return
        if self._task is not None and not self._task.done():
            return
        now = datetime.now(timezone.utc)
        self._state.next_run_at_utc = now.isoformat()
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
        if not self._state.enabled:
            self._state.last_result = "disabled"
            return
        if self._state.running:
            logger.info("Skipping heartbeat tick: previous run still active")
            return

        async def _execute() -> None:
            from sqlalchemy import select as sa_select, tuple_
            from backend.database import ChatSession as SessionModel, get_session
            from backend.session_store import append_session_message, get_or_create_session

            self._state.running = True
            started_at = datetime.now(timezone.utc)
            self._state.last_run_at_utc = started_at.isoformat()
            try:
                async for db in get_session():
                    dispatch_queue: list[tuple[str, str, str]] = []
                    users = (
                        await db.execute(
                            sa_select(SessionModel.user_id)
                            .where(
                                tuple_(SessionModel.platform, SessionModel.status).in_(
                                    [("web", "active"), ("web", "idle")]
                                )
                            )
                            .distinct()
                        )
                    ).all()
                    prompt = build_heartbeat_prompt(now=datetime.now(timezone.utc))
                    for (user_id,) in users:
                        row = await get_or_create_session(
                            db,
                            user_id=user_id,
                            platform="web",
                            session_id=HEARTBEAT_SESSION_ID,
                            title="heartbeat",
                            parent_session_id="agent:main:main",
                        )
                        await append_session_message(
                            db,
                            session_ref_id=row.id,
                            role="user",
                            content=prompt,
                            metadata={"source": "heartbeat_scheduler", "session": HEARTBEAT_SESSION_ID},
                        )
                        dispatch_queue.append((user_id, HEARTBEAT_SESSION_ID, prompt))
                    await db.commit()
                    for dispatch_user_id, dispatch_session_id, dispatch_prompt in dispatch_queue:
                        await self._dispatch(dispatch_user_id, dispatch_session_id, dispatch_prompt)
                    self._state.last_result = "ok"
            finally:
                self._state.running = False

        try:
            await asyncio.wait_for(_execute(), timeout=self._timeout_seconds)
            self._state.retries = 0
            self._state.next_run_at_utc = (datetime.now(timezone.utc)).isoformat()
        except Exception as exc:
            self._state.retries += 1
            self._state.last_result = "error"
            logger.warning("Heartbeat session run failed (attempt=%s): %s", self._state.retries, exc)
            if self._state.retries <= self._retry_cap:
                await asyncio.sleep(1)
                await self.run_once()

    def status_snapshot(self) -> dict[str, str | bool | int | None]:
        """Return a serializable runtime status for UI and health endpoints."""
        return {
            "enabled": self._state.enabled,
            "running": self._state.running,
            "retries": self._state.retries,
            "last_run_at": self._state.last_run_at_utc,
            "next_run_at": self._state.next_run_at_utc,
            "last_result": self._state.last_result,
        }
