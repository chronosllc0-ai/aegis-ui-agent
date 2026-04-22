"""Subscriber fan-out for the always-on runtime.

Every surface (websocket, Slack egress, Telegram bot, heartbeat, etc.)
that wants to observe a session registers a :class:`Subscriber` with
:class:`FanOut`. When the dispatch hook emits a runtime event, FanOut
pushes it to every active subscriber.

For Phase 2 the fan-out is in-process and deliberately minimal:

* No retry / redelivery — surfaces that need durability should read back
  from :mod:`backend.runtime.persistence`.
* No channel filtering — subscribers receive every event for their
  session and drop what they don't care about.
* Bad subscribers are logged + evicted so one flaky listener can't
  break the session.

The smoke test relies on this to assert "event reached a test
subscriber", which is the Phase 2 acceptance criterion.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


SubscriberCallback = Callable[["RuntimeEvent"], Awaitable[None]]


@dataclass
class RuntimeEvent:
    """A structured event emitted by the agent loop."""

    kind: str
    """``user_message`` | ``delta`` | ``tool_call`` | ``tool_result`` |
    ``final_message`` | ``error`` | ``run_started`` | ``run_completed``."""

    session_id: str
    owner_uid: str | None = None
    channel: str = "web"
    run_id: str | None = None
    seq: int = 0
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Subscriber:
    name: str
    callback: SubscriberCallback


class FanOut:
    """Register subscribers and dispatch events to all of them."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._lock = asyncio.Lock()

    async def subscribe(self, subscriber: Subscriber) -> None:
        async with self._lock:
            self._subscribers.append(subscriber)

    async def unsubscribe(self, name: str) -> None:
        async with self._lock:
            self._subscribers = [s for s in self._subscribers if s.name != name]

    async def publish(self, event: RuntimeEvent) -> None:
        async with self._lock:
            subscribers = list(self._subscribers)
        if not subscribers:
            return
        results = await asyncio.gather(
            *(self._deliver(sub, event) for sub in subscribers),
            return_exceptions=True,
        )
        bad: list[str] = []
        for sub, result in zip(subscribers, results):
            if isinstance(result, Exception):
                logger.warning(
                    "FanOut subscriber %s failed delivering %s: %s",
                    sub.name,
                    event.kind,
                    result,
                )
                bad.append(sub.name)
        if bad:
            async with self._lock:
                self._subscribers = [s for s in self._subscribers if s.name not in bad]

    @staticmethod
    async def _deliver(sub: Subscriber, event: RuntimeEvent) -> None:
        await sub.callback(event)

    def __len__(self) -> int:
        return len(self._subscribers)


class FanOutRegistry:
    """Per-session FanOut instances, keyed by session_id."""

    def __init__(self) -> None:
        self._by_session: dict[str, FanOut] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> FanOut:
        async with self._lock:
            fanout = self._by_session.get(session_id)
            if fanout is None:
                fanout = FanOut()
                self._by_session[session_id] = fanout
            return fanout

    async def drop(self, session_id: str) -> None:
        async with self._lock:
            self._by_session.pop(session_id, None)


__all__ = [
    "RuntimeEvent",
    "Subscriber",
    "FanOut",
    "FanOutRegistry",
]
