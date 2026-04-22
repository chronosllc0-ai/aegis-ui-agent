"""Channel session model.

A :class:`ChannelSession` is the durable unit of state for one surface in
one user's agent runtime. One user has many channel sessions (web, slack,
telegram, discord, heartbeat, ...), all managed by the same
:class:`~backend.runtime.supervisor.SessionSupervisor`.

The supervisor itself owns **one** persistent agent session per user.
Channel sessions are subscribers and producers into that shared agent
session, not isolated conversations. See ``PLAN.md §2.0``.

Phase 1 implementation: this module carries the minimal dataclasses,
identifier helpers, and an in-memory store. Postgres persistence lands
in Phase 1 migration step; compaction checkpointing and context-meter
snapshots land in Phase 7 / Phase 8.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable


VALID_CHANNELS: frozenset[str] = frozenset(
    {"web", "slack", "telegram", "discord", "heartbeat", "webhook", "automation", "subagent"}
)


@dataclass(frozen=True)
class ChannelSessionKey:
    """Stable composite key for a channel session.

    Matches the session id format used in the existing backend (see
    :mod:`backend.session_identity`) but is scoped to the (owner, channel)
    pair used by the always-on runtime. The third axis (chat_type /
    peer_id) is left on the underlying :class:`ChannelSession.metadata`
    where surface-specific adapters need it.
    """

    owner_uid: str
    channel: str

    def __post_init__(self) -> None:
        if not self.owner_uid:
            raise ValueError("owner_uid is required")
        if self.channel not in VALID_CHANNELS:
            raise ValueError(f"unknown channel: {self.channel!r}")

    def to_session_id(self) -> str:
        """Serialize to a canonical string session id."""
        return f"agent:main:{self.channel}:{self.owner_uid}"


@dataclass
class ChannelSession:
    """Durable per-(owner, channel) runtime state.

    The fields listed here are the Phase 1 minimum; subsequent phases
    will add ``compaction_state``, ``context_meter``, and a persistent
    message log.
    """

    key: ChannelSessionKey
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    """Free-form channel-specific data (e.g. slack workspace id)."""

    subscribers: set[str] = field(default_factory=set)
    """Egress subscriber ids (websocket connection ids, bot tokens, etc.)."""

    paused: bool = False
    """When true, new events are queued but not dispatched to the loop."""

    @property
    def session_id(self) -> str:
        return self.key.to_session_id()

    @property
    def owner_uid(self) -> str:
        return self.key.owner_uid

    @property
    def channel(self) -> str:
        return self.key.channel

    def touch(self) -> None:
        """Update ``last_activity_at`` to now."""
        self.last_activity_at = time.time()

    def add_subscriber(self, subscriber_id: str) -> None:
        self.subscribers.add(subscriber_id)
        self.touch()

    def remove_subscriber(self, subscriber_id: str) -> None:
        self.subscribers.discard(subscriber_id)
        self.touch()

    def describe(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot for admin/debug endpoints."""
        return {
            "session_id": self.session_id,
            "owner_uid": self.owner_uid,
            "channel": self.channel,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "subscribers": sorted(self.subscribers),
            "paused": self.paused,
            "metadata": dict(self.metadata),
        }


class InMemoryChannelSessionStore:
    """Process-local store used by the Phase 1 supervisor.

    A real persistent store lands later; this class exists to give the
    supervisor a stable API now so future phases can swap the backing
    implementation without touching call sites.
    """

    def __init__(self) -> None:
        self._sessions: dict[ChannelSessionKey, ChannelSession] = {}

    def get(self, key: ChannelSessionKey) -> ChannelSession | None:
        return self._sessions.get(key)

    def get_or_create(self, key: ChannelSessionKey) -> ChannelSession:
        existing = self._sessions.get(key)
        if existing is not None:
            return existing
        session = ChannelSession(key=key)
        self._sessions[key] = session
        return session

    def list_for_owner(self, owner_uid: str) -> list[ChannelSession]:
        return [s for s in self._sessions.values() if s.owner_uid == owner_uid]

    def delete(self, key: ChannelSessionKey) -> bool:
        return self._sessions.pop(key, None) is not None

    def __len__(self) -> int:
        return len(self._sessions)

    def __iter__(self) -> Iterable[ChannelSession]:  # pragma: no cover - trivial
        return iter(self._sessions.values())
