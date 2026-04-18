"""In-memory runtime telemetry counters for rollout safety and observability."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import time
from typing import Any, Deque
from uuid import uuid4


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


@dataclass(slots=True)
class RuntimeEvent:
    """Single in-memory observability event row."""

    id: str
    ts: float
    category: str
    subsystem: str
    level: str
    message: str
    session_id: str | None = None
    request_id: str | None = None
    task_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class RuntimeEventStore:
    """In-memory event log store with TTL retention and offset pagination."""

    def __init__(self, *, ttl_seconds: int = 3600, max_events: int = 5000) -> None:
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.max_events = max(100, int(max_events))
        self._events: Deque[RuntimeEvent] = deque()

    def _prune(self, now: float | None = None) -> None:
        threshold = (now if now is not None else time.time()) - self.ttl_seconds
        while self._events and self._events[0].ts < threshold:
            self._events.popleft()
        while len(self._events) > self.max_events:
            self._events.popleft()

    def append(
        self,
        *,
        category: str,
        subsystem: str,
        level: str,
        message: str,
        session_id: str | None = None,
        request_id: str | None = None,
        task_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> RuntimeEvent:
        """Append a new event and enforce retention constraints."""
        now = time.time()
        event = RuntimeEvent(
            id=str(uuid4()),
            ts=now,
            category=str(category or "runtime").strip().lower() or "runtime",
            subsystem=str(subsystem or "system").strip().lower() or "system",
            level=str(level or "info").strip().lower() or "info",
            message=str(message or "event").strip() or "event",
            session_id=str(session_id).strip() if session_id else None,
            request_id=str(request_id).strip() if request_id else None,
            task_id=str(task_id).strip() if task_id else None,
            details=dict(details or {}),
        )
        self._events.append(event)
        self._prune(now)
        return event

    def list_events(
        self,
        *,
        session_id: str | None = None,
        subsystem: str | None = None,
        level: str | None = None,
        limit: int = 50,
        cursor: int = 0,
    ) -> dict[str, Any]:
        """List events with optional filters and offset cursor pagination."""
        self._prune()
        normalized_session = str(session_id or "").strip() or None
        normalized_subsystem = str(subsystem or "").strip().lower() or None
        normalized_level = str(level or "").strip().lower() or None
        page_limit = min(max(1, int(limit)), 200)
        page_cursor = max(0, int(cursor))

        filtered = [
            event
            for event in reversed(self._events)
            if (not normalized_session or event.session_id == normalized_session)
            and (not normalized_subsystem or event.subsystem == normalized_subsystem)
            and (not normalized_level or event.level == normalized_level)
        ]
        total = len(filtered)
        page = filtered[page_cursor : page_cursor + page_limit]
        next_cursor = page_cursor + len(page)
        return {
            "events": [
                {
                    "id": event.id,
                    "ts": event.ts,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(event.ts)),
                    "category": event.category,
                    "subsystem": event.subsystem,
                    "level": event.level,
                    "message": event.message,
                    "session_id": event.session_id,
                    "request_id": event.request_id,
                    "task_id": event.task_id,
                    "details": event.details,
                }
                for event in page
            ],
            "pagination": {
                "cursor": page_cursor,
                "next_cursor": next_cursor if next_cursor < total else None,
                "limit": page_limit,
                "total": total,
                "has_more": next_cursor < total,
            },
            "retention": {
                "ttl_seconds": self.ttl_seconds,
                "max_events": self.max_events,
            },
        }
