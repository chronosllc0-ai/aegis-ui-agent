"""Agent event model for the always-on runtime.

Every inbound signal the agent reacts to — chat messages (from any
surface), heartbeats, webhooks, automations, subagent callbacks — becomes
an :class:`AgentEvent` on the per-user :class:`~backend.runtime.supervisor.SessionSupervisor`
inbox. The supervisor owns scheduling and dispatch.

This module is *only* a data model. No I/O, no async, no side effects.
Phase 1 keeps it deliberately tiny; later phases will extend the event
schema with identity, tool approvals, and compaction signals without
changing the top-level dataclass shape.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


class EventKind(str, enum.Enum):
    """The kind of trigger that produced this event."""

    CHAT_MESSAGE = "chat_message"
    HEARTBEAT = "heartbeat"
    WEBHOOK = "webhook"
    AUTOMATION = "automation"
    SUBAGENT_RESULT = "subagent_result"
    TOOL_APPROVAL = "tool_approval"
    STOP = "stop"
    USER_INPUT_RESPONSE = "user_input_response"


class EventPriority(enum.IntEnum):
    """Relative priority for events competing for the agent loop.

    Lower numbers run first. The default priority ladder matches the
    design in ``PLAN.md §2.0``: user chat messages preempt webhooks,
    webhooks preempt heartbeats, heartbeats preempt other background
    work. Tie-breaking falls back to ``created_at``.
    """

    USER_CHAT = 10
    TOOL_APPROVAL = 15
    WEBHOOK = 30
    HEARTBEAT = 50
    AUTOMATION = 60
    BACKGROUND = 100


_DEFAULT_PRIORITY_FOR_KIND: dict[EventKind, EventPriority] = {
    EventKind.CHAT_MESSAGE: EventPriority.USER_CHAT,
    EventKind.HEARTBEAT: EventPriority.HEARTBEAT,
    EventKind.WEBHOOK: EventPriority.WEBHOOK,
    EventKind.AUTOMATION: EventPriority.AUTOMATION,
    EventKind.SUBAGENT_RESULT: EventPriority.USER_CHAT,
    EventKind.TOOL_APPROVAL: EventPriority.TOOL_APPROVAL,
    EventKind.STOP: EventPriority.USER_CHAT,
    EventKind.USER_INPUT_RESPONSE: EventPriority.USER_CHAT,
}


@dataclass(frozen=True)
class AgentEvent:
    """An atomic signal destined for the per-user agent loop.

    Attributes
    ----------
    event_id:
        Stable identifier assigned at creation. Surfaces that need to
        correlate a response back to the originating event (e.g. Slack
        threads, WS clients awaiting a streamed reply) carry this id.
    owner_uid:
        The user account that owns the event. The ``SessionSupervisor``
        indexes inboxes by this value.
    channel:
        Which surface produced the event (``web``, ``slack``, ``telegram``,
        ``discord``, ``heartbeat``, ``webhook``, ``automation``, ``subagent``).
        Channels are *subscribers* and *producers* on the same session —
        see PLAN.md §2.0.
    kind:
        Structural kind, used for routing + priority.
    priority:
        Queue priority. Leave ``None`` to default from ``kind``.
    payload:
        Free-form JSON-serializable payload. For chat messages this
        typically contains ``{"text": "...", "attachments": [...]}``; for
        heartbeats it may be empty.
    reply_hint:
        Optional routing hint telling egress where to render replies
        (e.g. ``{"slack_thread_ts": "...", "channel_id": "..."}``).
        When absent, egress fans out to whatever subscribers are bound
        to the channel.
    correlation_id:
        Optional external correlation id (e.g. an upstream request id).
    created_at:
        Wall-clock time of event creation (seconds since epoch).
    """

    owner_uid: str
    channel: str
    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)
    reply_hint: dict[str, Any] | None = None
    correlation_id: str | None = None
    priority: EventPriority | None = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)

    def effective_priority(self) -> EventPriority:
        """Return the priority this event should queue at."""
        if self.priority is not None:
            return self.priority
        return _DEFAULT_PRIORITY_FOR_KIND.get(self.kind, EventPriority.BACKGROUND)

    def __lt__(self, other: "AgentEvent") -> bool:
        """Priority + created_at comparator suitable for ``PriorityQueue``."""
        if not isinstance(other, AgentEvent):
            return NotImplemented
        self_key = (int(self.effective_priority()), self.created_at, self.event_id)
        other_key = (int(other.effective_priority()), other.created_at, other.event_id)
        return self_key < other_key
