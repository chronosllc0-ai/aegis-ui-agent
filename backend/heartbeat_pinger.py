"""Background heartbeat pinger for Aegis.

Checks all user automations every `interval_seconds` and fires tasks that are due
according to their cron schedule via the provided dispatch callback.

Uses `croniter` for cron evaluation. Natural-language schedules (e.g. "9am every
weekday") are normalised to cron expressions automatically.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Natural-language → cron mappings (checked in order; first match wins)
_NL_TO_CRON: list[tuple[str, str]] = [
    ("every minute", "* * * * *"),
    ("every hour", "0 * * * *"),
    ("every weekday", "0 9 * * 1-5"),
    ("weekdays", "0 9 * * 1-5"),
    ("every monday", "0 9 * * 1"),
    ("every tuesday", "0 9 * * 2"),
    ("every wednesday", "0 9 * * 3"),
    ("every thursday", "0 9 * * 4"),
    ("every friday", "0 9 * * 5"),
    ("every weekend", "0 10 * * 6,0"),
    ("every morning", "0 8 * * *"),
    ("every night", "0 21 * * *"),
    ("every week", "0 9 * * 1"),
    ("every day", "0 9 * * *"),
    ("daily", "0 9 * * *"),
]

_CRON_RE = re.compile(r"^[\d\*\/\-\,]+ [\d\*\/\-\,]+ [\d\*\/\-\,]+ [\d\*\/\-\,]+ [\d\*\/\-\,]+$")
_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.IGNORECASE)


def _extract_hhmm(text: str) -> tuple[int, int] | None:
    m = _TIME_RE.search(text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = m.group(3).lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return hour, minute


def normalize_schedule(schedule: str) -> str:
    """Convert a natural-language schedule or verify a cron expression."""
    s = schedule.strip()
    if _CRON_RE.match(s):
        return s  # already a valid 5-field cron expression
    lower = s.lower()
    for phrase, cron_template in _NL_TO_CRON:
        if phrase in lower:
            parts = cron_template.split()
            hhmm = _extract_hhmm(lower)
            if hhmm and phrase not in ("every minute", "every hour"):
                parts[0] = str(hhmm[1])  # minute
                parts[1] = str(hhmm[0])  # hour
            return " ".join(parts)
    logger.warning("Cannot parse schedule '%s', defaulting to daily 9 AM", schedule)
    return "0 9 * * *"


TaskDispatcher = Callable[[str, str], Awaitable[None]]


class HeartbeatPinger:
    """Fires due automations every `interval_seconds`."""

    def __init__(self, dispatch: TaskDispatcher, interval_seconds: int = 60) -> None:
        self._dispatch = dispatch
        self._interval = interval_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("HeartbeatPinger started (interval=%ds)", self._interval)

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("HeartbeatPinger tick failed")
            await asyncio.sleep(self._interval)

    async def _tick(self) -> None:
        try:
            from croniter import croniter  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("croniter not installed — heartbeat pinger disabled. pip install croniter>=3.0.0")
            return

        from backend.user_memory import (
            list_all_sessions_with_automations,
            load_automations,
            save_automations,
        )

        now = datetime.now(timezone.utc)
        for session_id in list_all_sessions_with_automations():
            automations = load_automations(session_id)
            updated = False
            for auto in automations:
                if not auto.get("enabled"):
                    continue
                cron_expr = normalize_schedule(auto.get("schedule", "0 9 * * *"))
                try:
                    cron = croniter(cron_expr, now)
                    prev_run: datetime = cron.get_prev(datetime)
                    last_run_str: str | None = auto.get("last_run")
                    last_run = datetime.fromisoformat(last_run_str) if last_run_str else None
                    seconds_since = (now - prev_run).total_seconds()
                    already_ran = last_run is not None and last_run >= prev_run
                    if seconds_since <= self._interval and not already_ran:
                        logger.info(
                            "Firing automation '%s' for session %s", auto.get("label"), session_id
                        )
                        auto["last_run"] = now.isoformat()
                        updated = True
                        await self._dispatch(session_id, str(auto.get("task", "")))
                except Exception:
                    logger.exception(
                        "Error evaluating automation %s for session %s", auto.get("id"), session_id
                    )
            if updated:
                save_automations(session_id, automations)
