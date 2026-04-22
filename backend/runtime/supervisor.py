"""SessionSupervisor: per-user always-on runtime.

Per ``PLAN.md §2.0``, each user has exactly one supervisor in memory,
regardless of how many surfaces (web / Slack / Telegram / Discord /
heartbeat / subagents) are talking to them. The supervisor owns:

- the per-(owner, channel) :class:`ChannelSession` store;
- a priority queue of inbound :class:`AgentEvent` instances;
- a single worker task that dispatches events to the agent loop.

Phase 1 implements the scaffolding only. ``dispatch`` is a no-op that
records the event; Phase 2 replaces it with the OpenAI Agents SDK
runner. The priority queue, queue-depth metrics, shutdown semantics, and
the shape of the dispatch hook are stable contracts from this phase on.

This module must remain importable without any database, websocket, or
agent-SDK dependency — tests rely on importing it standalone.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from backend.runtime.events import AgentEvent
from backend.runtime.session import (
    ChannelSession,
    ChannelSessionKey,
    InMemoryChannelSessionStore,
)

logger = logging.getLogger(__name__)


DispatchHook = Callable[["SessionSupervisor", AgentEvent, ChannelSession], Awaitable[None]]
"""Callable signature for the agent-loop dispatcher.

Phase 2 installs the real hook (OpenAI Agents SDK runner). Until then
the supervisor uses :func:`_noop_dispatch` which simply logs the event
and returns.
"""


async def _noop_dispatch(
    supervisor: "SessionSupervisor",
    event: AgentEvent,
    session: ChannelSession,
) -> None:
    """Default dispatcher: log and return.

    Phase 1 deliberately does not process events. The goal is to prove
    out priority ordering, session materialization, and shutdown without
    risk of collateral damage to the legacy runtime.
    """
    logger.info(
        "SessionSupervisor(%s) received %s on %s (priority=%s) — dispatch disabled in Phase 1",
        supervisor.owner_uid,
        event.kind.value,
        session.session_id,
        event.effective_priority().name,
    )


@dataclass
class SupervisorStats:
    """Lightweight counters for observability."""

    enqueued: int = 0
    processed: int = 0
    errors: int = 0
    last_event_id: str | None = None

    def as_dict(self) -> dict[str, int | str | None]:
        return {
            "enqueued": self.enqueued,
            "processed": self.processed,
            "errors": self.errors,
            "last_event_id": self.last_event_id,
        }


class SessionSupervisor:
    """One per user. Owns channel sessions + an event queue."""

    def __init__(
        self,
        owner_uid: str,
        *,
        dispatch: DispatchHook | None = None,
        session_store: InMemoryChannelSessionStore | None = None,
    ) -> None:
        if not owner_uid:
            raise ValueError("owner_uid is required")
        self.owner_uid = owner_uid
        self._sessions = session_store or InMemoryChannelSessionStore()
        self._dispatch: DispatchHook = dispatch or _noop_dispatch
        self._inbox: asyncio.PriorityQueue[AgentEvent] = asyncio.PriorityQueue()
        self._worker: asyncio.Task[None] | None = None
        self._shutdown = asyncio.Event()
        self.stats = SupervisorStats()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background worker. Idempotent."""
        if self._worker is not None and not self._worker.done():
            return
        self._shutdown.clear()
        loop = asyncio.get_event_loop()
        self._worker = loop.create_task(self._run(), name=f"supervisor-{self.owner_uid}")

    async def stop(self, *, drain: bool = True) -> None:
        """Stop the background worker.

        When ``drain=True`` the worker finishes the current event and
        processes any queued events in priority order before exiting.
        """
        self._shutdown.set()
        if drain:
            # Sentinel wakes the worker to re-check ``_shutdown``.
            await self._inbox.put(_SHUTDOWN_SENTINEL)
        if self._worker is not None:
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    # ------------------------------------------------------------------
    # Session access
    # ------------------------------------------------------------------

    def session(self, channel: str) -> ChannelSession:
        """Return (or create) the session for ``channel`` under this owner."""
        key = ChannelSessionKey(owner_uid=self.owner_uid, channel=channel)
        return self._sessions.get_or_create(key)

    def sessions(self) -> list[ChannelSession]:
        return self._sessions.list_for_owner(self.owner_uid)

    # ------------------------------------------------------------------
    # Event ingress
    # ------------------------------------------------------------------

    async def enqueue(self, event: AgentEvent) -> None:
        """Add an event to the priority queue.

        Materializes the target :class:`ChannelSession` before enqueueing
        so the supervisor has an immediate, consistent view of who is
        talking to it.
        """
        if event.owner_uid != self.owner_uid:
            raise ValueError(
                f"event owner {event.owner_uid!r} does not match supervisor {self.owner_uid!r}"
            )
        self.session(event.channel)  # warm the session
        self.stats.enqueued += 1
        self.stats.last_event_id = event.event_id
        await self._inbox.put(event)

    def queue_depth(self) -> int:
        return self._inbox.qsize()

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        logger.info("SessionSupervisor(%s) worker starting", self.owner_uid)
        try:
            while not self._shutdown.is_set():
                event = await self._inbox.get()
                if event is _SHUTDOWN_SENTINEL:
                    # Shutdown requested; loop exits naturally.
                    continue
                session = self.session(event.channel)
                session.touch()
                try:
                    await self._dispatch(self, event, session)
                    self.stats.processed += 1
                except Exception:
                    self.stats.errors += 1
                    logger.exception(
                        "SessionSupervisor(%s) dispatch raised for %s",
                        self.owner_uid,
                        event.event_id,
                    )
        finally:
            logger.info(
                "SessionSupervisor(%s) worker exiting (stats=%s)",
                self.owner_uid,
                self.stats.as_dict(),
            )

    # ------------------------------------------------------------------
    # Test / admin affordances
    # ------------------------------------------------------------------

    def install_dispatch(self, hook: DispatchHook) -> None:
        """Replace the dispatcher. Used by Phase 2 and by tests."""
        self._dispatch = hook


class _ShutdownSentinel(AgentEvent):
    """Sentinel used to wake the worker on shutdown."""

    __slots__ = ()


# A real sentinel uses a minimally-constructed AgentEvent so the
# PriorityQueue comparator still works.
from backend.runtime.events import EventKind  # noqa: E402  (deliberate late import)

_SHUTDOWN_SENTINEL = AgentEvent(
    owner_uid="__supervisor__",
    channel="web",
    kind=EventKind.STOP,
    payload={"__shutdown__": True},
)


class SupervisorRegistry:
    """Process-wide registry of per-user supervisors.

    Phase 1 is single-process. Later phases can replace this with a
    distributed coordinator (Redis lock, dedicated worker pool) without
    changing call sites.
    """

    def __init__(self, *, dispatch: DispatchHook | None = None) -> None:
        self._supervisors: dict[str, SessionSupervisor] = {}
        self._dispatch = dispatch
        self._lock = asyncio.Lock()

    async def get(self, owner_uid: str) -> SessionSupervisor:
        """Return (or lazily create + start) the supervisor for ``owner_uid``."""
        async with self._lock:
            existing = self._supervisors.get(owner_uid)
            if existing is not None:
                return existing
            supervisor = SessionSupervisor(owner_uid, dispatch=self._dispatch)
            supervisor.start()
            self._supervisors[owner_uid] = supervisor
            return supervisor

    async def shutdown(self) -> None:
        """Stop every supervisor in the registry."""
        async with self._lock:
            supervisors = list(self._supervisors.values())
            self._supervisors.clear()
        await asyncio.gather(*(s.stop() for s in supervisors), return_exceptions=True)

    def describe(self) -> dict[str, dict[str, int | str | None]]:
        """Return per-supervisor stats for admin."""
        return {uid: s.stats.as_dict() for uid, s in self._supervisors.items()}

    def __len__(self) -> int:
        return len(self._supervisors)
