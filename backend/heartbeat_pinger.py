"""Background heartbeat pinger — checks all user automations every 60s
and fires due tasks via the operations queue.

Uses croniter for cron expression matching. Natural language schedules
(e.g. "every weekday at 9am") are pre-parsed to cron expressions on creation
or converted on-the-fly with a simple mapper.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Maps common natural language → cron
NL_TO_CRON: dict[str, str] = {
    "every minute": "* * * * *",
    "every hour": "0 * * * *",
    "every day": "0 9 * * *",
    "daily": "0 9 * * *",
    "every weekday": "0 9 * * 1-5",
    "every monday": "0 9 * * 1",
    "every tuesday": "0 9 * * 2",
    "every wednesday": "0 9 * * 3",
    "every thursday": "0 9 * * 4",
    "every friday": "0 9 * * 5",
    "every weekend": "0 10 * * 6,0",
    "every morning": "0 8 * * *",
    "every night": "0 21 * * *",
    "every week": "0 9 * * 1",
}


def _parse_time_in_schedule(schedule: str) -> str | None:
    """Extract HH:MM from schedules like '9am every weekday'."""
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', schedule.lower())
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        if m.group(3) == 'pm' and hour != 12:
            hour += 12
        elif m.group(3) == 'am' and hour == 12:
            hour = 0
        return f"{minute} {hour}"
    return None


def normalize_schedule(schedule: str) -> str:
    """Convert natural language schedule to cron expression."""
    s = schedule.strip().lower()
    # Direct lookup
    for phrase, cron in NL_TO_CRON.items():
        if phrase in s:
            time_part = _parse_time_in_schedule(s)
            if time_part and phrase not in ("every minute", "every hour"):
                parts = cron.split()
                time_fields = time_part.split()
                parts[0] = time_fields[0]  # minute
                parts[1] = time_fields[1]  # hour
                return " ".join(parts)
            return cron
    # Already looks like a cron expression (5 space-separated fields)
    if re.match(r'^[\d\*\/\-\,]+ [\d\*\/\-\,]+ [\d\*\/\-\,]+ [\d\*\/\-\,]+ [\d\*\/\-\,]+$', s):
        return s
    # Fallback: daily at 9am
    logger.warning("Could not parse schedule '%s', defaulting to daily 9am", schedule)
    return "0 9 * * *"


TaskDispatcher = Callable[[str, str], Coroutine[Any, Any, None]]


class HeartbeatPinger:
    """Checks all user automations every `interval_seconds` and fires due tasks."""

    def __init__(self, dispatch: TaskDispatcher, interval_seconds: int = 60) -> None:
        self._dispatch = dispatch
        self._interval = interval_seconds
        self._running = False
        self._task: asyncio.Task | None = None

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
                await self._check_all()
            except Exception:
                logger.exception("HeartbeatPinger check failed")
            await asyncio.sleep(self._interval)

    async def _check_all(self) -> None:
        try:
            from croniter import croniter
        except ImportError:
            logger.warning("croniter not installed — heartbeat pinger disabled. Run: pip install croniter")
            return

        from backend.user_memory import list_all_sessions_with_automations, load_automations, save_automations

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
                    prev_run = cron.get_prev(datetime)
                    last_run_str = auto.get("last_run")
                    last_run = datetime.fromisoformat(last_run_str) if last_run_str else None
                    # Fire if prev_run is within the last interval_seconds and hasn't run yet
                    seconds_since_prev = (now - prev_run).total_seconds()
                    if seconds_since_prev <= self._interval and (last_run is None or last_run < prev_run):
                        logger.info("Firing automation '%s' for session %s", auto.get("label"), session_id)
                        auto["last_run"] = now.isoformat()
                        updated = True
                        await self._dispatch(session_id, auto["task"])
                except Exception:
                    logger.exception("Error evaluating automation %s for session %s", auto.get("id"), session_id)
            if updated:
                save_automations(session_id, automations)
