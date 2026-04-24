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
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from backend.runtime.events import AgentEvent, EventKind
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


# A minimally-constructed AgentEvent acts as the wake sentinel. It is
# identified by the boolean flag on its payload and never dispatched.
_SHUTDOWN_SENTINEL: AgentEvent = AgentEvent(
    owner_uid="__supervisor__",
    channel="web",
    kind=EventKind.STOP,
    payload={"__shutdown__": True},
)


def _is_shutdown_sentinel(event: AgentEvent) -> bool:
    return event is _SHUTDOWN_SENTINEL or (
        event.owner_uid == "__supervisor__" and bool(event.payload.get("__shutdown__"))
    )


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
        persistence_factory: Callable[[], Any] | None = None,
    ) -> None:
        if not owner_uid:
            raise ValueError("owner_uid is required")
        self.owner_uid = owner_uid
        self._sessions = session_store or InMemoryChannelSessionStore()
        self._dispatch: DispatchHook = dispatch or _noop_dispatch
        # Optional async-session factory (``async def () -> AsyncSession``
        # or ``() -> AsyncContextManager[AsyncSession]``). When set, the
        # supervisor persists every enqueued :class:`AgentEvent` to the
        # ``runtime_inbox_events`` table so Phase 7 rehydration can
        # replay unfinished work after a crash.
        self._persistence_factory: Callable[[], Any] | None = persistence_factory
        self._inbox: asyncio.PriorityQueue[AgentEvent] = asyncio.PriorityQueue()
        self._worker: asyncio.Task[None] | None = None
        # Event flags used to coordinate shutdown semantics. ``_draining``
        # signals "stop taking new work once the current queue drains";
        # ``_stopping`` signals "exit ASAP, abandon the queue".
        self._draining = asyncio.Event()
        self._stopping = asyncio.Event()
        self.stats = SupervisorStats()
        # Optional async teardown callbacks. Populated by the agent loop
        # (:mod:`backend.runtime.agent_loop`) so per-supervisor MCP tool
        # providers, database pools, etc. can be released when the
        # supervisor stops. Registered callables are awaited in LIFO
        # order during :meth:`stop`; errors are logged but do not abort
        # the shutdown sequence.
        self._teardown_hooks: list[Callable[[], Awaitable[None]]] = []

    def register_teardown(self, hook: Callable[[], Awaitable[None]]) -> None:
        """Register an async callback to run when the supervisor stops."""
        self._teardown_hooks.append(hook)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background worker. Idempotent."""
        if self._worker is not None and not self._worker.done():
            return
        self._draining.clear()
        self._stopping.clear()
        loop = asyncio.get_event_loop()
        self._worker = loop.create_task(self._run(), name=f"supervisor-{self.owner_uid}")

    async def stop(self, *, drain: bool = True) -> None:
        """Stop the background worker.

        When ``drain=True`` the worker processes any queued events in
        priority order, then exits (subsequent :meth:`enqueue` calls are
        rejected). When ``drain=False`` the worker exits as soon as it
        wakes up — any queued events that have not been pulled off the
        queue are abandoned.

        Safe to call when the worker is not running.
        """
        if drain:
            self._draining.set()
        else:
            self._stopping.set()
        # Always push a sentinel so a worker blocked on ``inbox.get()``
        # wakes up and re-checks the shutdown flags.
        await self._inbox.put(_SHUTDOWN_SENTINEL)
        worker = self._worker
        if worker is None:
            return
        try:
            await worker
        except asyncio.CancelledError:
            pass
        finally:
            self._worker = None
            # Fire teardown hooks in reverse registration order.
            hooks = list(reversed(self._teardown_hooks))
            self._teardown_hooks.clear()
            for hook in hooks:
                try:
                    await hook()
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "SessionSupervisor(%s) teardown hook raised",
                        self.owner_uid,
                    )

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

        Raises ``RuntimeError`` if the supervisor is shutting down.
        """
        if event.owner_uid != self.owner_uid:
            raise ValueError(
                f"event owner {event.owner_uid!r} does not match supervisor {self.owner_uid!r}"
            )
        if self._stopping.is_set() or self._draining.is_set():
            raise RuntimeError(
                f"SessionSupervisor({self.owner_uid}) is shutting down; refusing new events"
            )
        channel_session = self.session(event.channel)  # warm the session
        # Persist the inbox row *before* queueing so a crash between
        # ``put`` and the worker pickup still leaves a rehydration trail.
        # Persistence failures must never reject an enqueue — the queue
        # is the source of truth for live dispatch; persistence is a
        # best-effort durability layer.
        if self._persistence_factory is not None:
            try:
                from backend.runtime.persistence import record_inbox_event

                async with self._persistence_factory() as db:
                    await record_inbox_event(
                        db, event, session_id=channel_session.session_id
                    )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "SessionSupervisor(%s) failed to persist inbox event %s",
                    self.owner_uid,
                    event.event_id,
                )
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
            while True:
                if self._stopping.is_set():
                    break
                if self._draining.is_set() and self._inbox.empty():
                    break
                event = await self._inbox.get()
                if _is_shutdown_sentinel(event):
                    # Wake signal; re-check shutdown flags at the top of
                    # the loop.
                    continue
                if self._stopping.is_set():
                    # Requested exit-now while we were blocked on get();
                    # drop the event on the floor.
                    break
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


class SupervisorRegistry:
    """Process-wide registry of per-user supervisors.

    Phase 1 is single-process. Later phases can replace this with a
    distributed coordinator (Redis lock, dedicated worker pool) without
    changing call sites.
    """

    def __init__(
        self,
        *,
        dispatch: DispatchHook | None = None,
        persistence_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._supervisors: dict[str, SessionSupervisor] = {}
        self._dispatch = dispatch
        self._persistence_factory = persistence_factory
        self._lock = asyncio.Lock()

    def set_persistence_factory(
        self, factory: Callable[[], Any] | None
    ) -> None:
        """Install the persistence factory used by new supervisors.

        Existing supervisors are updated in place so the first crash
        after install still captures inbox rows.
        """
        self._persistence_factory = factory
        for supervisor in self._supervisors.values():
            supervisor._persistence_factory = factory  # type: ignore[attr-defined]

    async def get(self, owner_uid: str) -> SessionSupervisor:
        """Return (or lazily create + start) the supervisor for ``owner_uid``."""
        async with self._lock:
            existing = self._supervisors.get(owner_uid)
            if existing is not None:
                return existing
            supervisor = SessionSupervisor(
                owner_uid,
                dispatch=self._dispatch,
                persistence_factory=self._persistence_factory,
            )
            supervisor.start()
            self._supervisors[owner_uid] = supervisor
            return supervisor

    async def shutdown(self) -> None:
        """Stop every supervisor in the registry, draining queued work."""
        async with self._lock:
            supervisors = list(self._supervisors.values())
            self._supervisors.clear()
        await asyncio.gather(
            *(s.stop(drain=True) for s in supervisors), return_exceptions=True
        )

    def describe(self) -> dict[str, dict[str, int | str | None]]:
        """Return per-supervisor stats for admin."""
        return {uid: s.stats.as_dict() for uid, s in self._supervisors.items()}

    def __len__(self) -> int:
        return len(self._supervisors)
