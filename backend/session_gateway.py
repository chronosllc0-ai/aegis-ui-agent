"""Single-port session event routing for live Aegis clients."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

SessionEventSender = Callable[[dict[str, Any]], Awaitable[bool]]


@dataclass(slots=True)
class SessionRoute:
    """Structured metadata for a connected live session."""

    session_id: str
    user_uid: str | None
    channel: str = "websocket"
    platform: str = "web"
    route_kind: str = "live_session"
    conversation_id: str | None = None
    created_at: float = field(default_factory=time.time)
    last_event_at: float = field(default_factory=time.time)
    lane_sequences: dict[str, int] = field(default_factory=dict)

    @property
    def session_key(self) -> str:
        owner = (self.user_uid or "anon").strip() or "anon"
        conversation = (self.conversation_id or "none").strip() or "none"
        return f"{self.route_kind}:{self.platform}:{owner}:{conversation}:{self.session_id}"

    def next_sequence(self, lane: str) -> int:
        next_value = self.lane_sequences.get(lane, 0) + 1
        self.lane_sequences[lane] = next_value
        self.last_event_at = time.time()
        return next_value


@dataclass(slots=True)
class LaneBuffer:
    """Buffered event state for a single session lane."""

    name: str
    queue: deque[dict[str, Any]] = field(default_factory=deque)
    enqueued: int = 0
    delivered: int = 0

    @property
    def pending(self) -> int:
        return len(self.queue)


@dataclass(slots=True)
class SessionRegistration:
    """Active live session registration."""

    route: SessionRoute
    send: SessionEventSender
    lane_buffers: dict[str, LaneBuffer] = field(default_factory=dict)
    wake_event: asyncio.Event = field(default_factory=asyncio.Event)
    drain_task: asyncio.Task[None] | None = None
    closed: bool = False
    last_delivery_error: str | None = None


class SessionEventHub:
    """Fan out runtime events to active browser sessions on the primary app port."""

    def __init__(self) -> None:
        self._registrations: dict[str, SessionRegistration] = {}
        self._user_sessions: dict[str, set[str]] = {}

    def register(
        self,
        session_id: str,
        *,
        user_uid: str | None,
        send: SessionEventSender,
        channel: str = "websocket",
        platform: str = "web",
        route_kind: str = "live_session",
    ) -> SessionRoute:
        registration = self._registrations.get(session_id)
        if registration is not None:
            self.unregister(session_id)
        route = SessionRoute(
            session_id=session_id,
            user_uid=user_uid,
            channel=channel,
            platform=platform,
            route_kind=route_kind,
        )
        registration = SessionRegistration(route=route, send=send)
        registration.drain_task = asyncio.create_task(self._drain_session(session_id))
        self._registrations[session_id] = registration
        if user_uid:
            self._user_sessions.setdefault(user_uid, set()).add(session_id)
        return route

    def unregister(self, session_id: str) -> None:
        registration = self._registrations.pop(session_id, None)
        if registration is None:
            return
        registration.closed = True
        registration.wake_event.set()
        if registration.drain_task is not None:
            registration.drain_task.cancel()
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

    def bind_conversation(self, session_id: str, conversation_id: str | None) -> None:
        registration = self._registrations.get(session_id)
        if registration is None:
            return
        registration.route.conversation_id = str(conversation_id).strip() or None
        registration.route.last_event_at = time.time()

    async def publish_to_session(self, session_id: str, event: dict[str, Any], *, lane: str = "main") -> bool:
        registration = self._registrations.get(session_id)
        if registration is None or registration.closed:
            return False
        lane_name = str(lane or "main").strip() or "main"
        envelope = self._envelope(registration.route, event, lane=lane_name)
        lane_buffer = registration.lane_buffers.setdefault(lane_name, LaneBuffer(name=lane_name))
        lane_buffer.queue.append(envelope)
        lane_buffer.enqueued += 1
        registration.wake_event.set()
        return True

    async def publish_to_user(self, user_uid: str, event: dict[str, Any], *, lane: str = "main") -> int:
        session_ids = list(self._user_sessions.get(user_uid, set()))
        if not session_ids:
            return 0
        delivered = 0
        for session_id in session_ids:
            if await self.publish_to_session(session_id, event, lane=lane):
                delivered += 1
        return delivered

    def snapshot(self) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for registration in self._registrations.values():
            snapshots.append(
                {
                    "session_id": registration.route.session_id,
                    "session_key": registration.route.session_key,
                    "user_uid": registration.route.user_uid,
                    "channel": registration.route.channel,
                    "platform": registration.route.platform,
                    "route_kind": registration.route.route_kind,
                    "conversation_id": registration.route.conversation_id,
                    "created_at": registration.route.created_at,
                    "last_event_at": registration.route.last_event_at,
                    "lane_sequences": dict(registration.route.lane_sequences),
                    "pending_by_lane": {
                        lane: buffer.pending
                        for lane, buffer in registration.lane_buffers.items()
                        if buffer.pending > 0
                    },
                    "delivered_by_lane": {
                        lane: buffer.delivered
                        for lane, buffer in registration.lane_buffers.items()
                        if buffer.delivered > 0
                    },
                    "last_delivery_error": registration.last_delivery_error,
                }
            )
        return sorted(snapshots, key=lambda item: (item["created_at"], item["session_id"]))

    async def _drain_session(self, session_id: str) -> None:
        try:
            while True:
                registration = self._registrations.get(session_id)
                if registration is None or registration.closed:
                    return
                await registration.wake_event.wait()
                while True:
                    registration = self._registrations.get(session_id)
                    if registration is None or registration.closed:
                        return
                    next_delivery = self._pop_next_delivery(registration)
                    if next_delivery is None:
                        registration.wake_event.clear()
                        if any(buffer.pending > 0 for buffer in registration.lane_buffers.values()):
                            registration.wake_event.set()
                        break
                    lane_name, payload = next_delivery
                    try:
                        delivered = await registration.send(payload)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        delivered = False
                        registration.last_delivery_error = str(exc)
                        logger.warning("Session event delivery failed session=%s lane=%s error=%s", session_id, lane_name, exc)
                    if delivered:
                        registration.last_delivery_error = None
                        lane_buffer = registration.lane_buffers.get(lane_name)
                        if lane_buffer is not None:
                            lane_buffer.delivered += 1
        except asyncio.CancelledError:
            return

    @staticmethod
    def _pop_next_delivery(registration: SessionRegistration) -> tuple[str, dict[str, Any]] | None:
        active_lanes = [lane for lane, buffer in registration.lane_buffers.items() if buffer.pending > 0]
        if not active_lanes:
            return None
        for lane in sorted(active_lanes):
            lane_buffer = registration.lane_buffers.get(lane)
            if lane_buffer is None or not lane_buffer.queue:
                continue
            return lane, lane_buffer.queue.popleft()
        return None

    def _envelope(self, route: SessionRoute, event: dict[str, Any], *, lane: str) -> dict[str, Any]:
        payload = dict(event)
        routing = {
            "session_id": route.session_id,
            "session_key": route.session_key,
            "lane": lane,
            "sequence": route.next_sequence(lane),
            "channel": route.channel,
            "platform": route.platform,
            "route_kind": route.route_kind,
            "conversation_id": route.conversation_id,
            "emitted_at": time.time(),
        }
        payload["routing"] = routing
        return payload
