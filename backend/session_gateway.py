"""Single-port session event routing for live Aegis clients."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

SessionEventSender = Callable[[dict[str, Any]], Awaitable[bool]]


@dataclass(slots=True)
class SessionRoute:
    """Structured metadata for a connected live session."""

    session_id: str
    user_uid: str | None
    channel: str = "websocket"
    created_at: float = field(default_factory=time.time)
    last_event_at: float = field(default_factory=time.time)
    lane_sequences: dict[str, int] = field(default_factory=dict)

    @property
    def session_key(self) -> str:
        owner = (self.user_uid or "anon").strip() or "anon"
        return f"web:{owner}:{self.session_id}"

    def next_sequence(self, lane: str) -> int:
        next_value = self.lane_sequences.get(lane, 0) + 1
        self.lane_sequences[lane] = next_value
        self.last_event_at = time.time()
        return next_value


@dataclass(slots=True)
class SessionRegistration:
    """Active live session registration."""

    route: SessionRoute
    send: SessionEventSender


class SessionEventHub:
    """Fan out runtime events to active browser sessions on the primary app port."""

    def __init__(self) -> None:
        self._registrations: dict[str, SessionRegistration] = {}
        self._user_sessions: dict[str, set[str]] = {}

    def register(self, session_id: str, *, user_uid: str | None, send: SessionEventSender, channel: str = "websocket") -> SessionRoute:
        route = SessionRoute(session_id=session_id, user_uid=user_uid, channel=channel)
        self._registrations[session_id] = SessionRegistration(route=route, send=send)
        if user_uid:
            self._user_sessions.setdefault(user_uid, set()).add(session_id)
        return route

    def unregister(self, session_id: str) -> None:
        registration = self._registrations.pop(session_id, None)
        if registration is None:
            return
        user_uid = registration.route.user_uid
        if not user_uid:
            return
        sessions = self._user_sessions.get(user_uid)
        if not sessions:
            return
        sessions.discard(session_id)
        if not sessions:
            self._user_sessions.pop(user_uid, None)

    def get_route(self, session_id: str) -> SessionRoute | None:
        registration = self._registrations.get(session_id)
        return registration.route if registration else None

    async def publish_to_session(self, session_id: str, event: dict[str, Any], *, lane: str = "main") -> bool:
        registration = self._registrations.get(session_id)
        if registration is None:
            return False
        envelope = self._envelope(registration.route, event, lane=lane)
        return await registration.send(envelope)

    async def publish_to_user(self, user_uid: str, event: dict[str, Any], *, lane: str = "main") -> int:
        session_ids = list(self._user_sessions.get(user_uid, set()))
        if not session_ids:
            return 0
        delivered = 0
        for session_id in session_ids:
            if await self.publish_to_session(session_id, event, lane=lane):
                delivered += 1
        return delivered

    def _envelope(self, route: SessionRoute, event: dict[str, Any], *, lane: str) -> dict[str, Any]:
        payload = dict(event)
        routing = {
            "session_id": route.session_id,
            "session_key": route.session_key,
            "lane": lane,
            "sequence": route.next_sequence(lane),
            "channel": route.channel,
            "emitted_at": time.time(),
        }
        data = payload.get("data")
        if isinstance(data, dict):
            payload["data"] = {**data, "_routing": routing}
        else:
            payload["routing"] = routing
        return payload
