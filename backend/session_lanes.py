"""Per-session lane queues for live/runtime task routing."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class QueuedInstruction:
    """A queued instruction tagged with routing metadata."""

    instruction: str
    lane: str = "default"
    source: str = "runtime"
    metadata: dict[str, Any] = field(default_factory=dict)
    queue_id: str = field(default_factory=lambda: str(uuid4()))
    enqueued_at: float = field(default_factory=time.time)


class SessionLaneQueue:
    """Round-robin lane queue for runtime instructions.

    Each lane maintains FIFO ordering while the dispatcher drains across lanes
    fairly. Snapshot/removal operations expose a flattened age-ordered view so
    existing queue UIs can keep simple index semantics.
    """

    def __init__(self, *, preferred_lanes: list[str] | None = None) -> None:
        self._queues: dict[str, deque[QueuedInstruction]] = {}
        self._lane_order: list[str] = list(preferred_lanes or ["interactive", "bot", "heartbeat", "background", "default"])
        self._round_robin_index = 0

    def __len__(self) -> int:
        return sum(len(queue) for queue in self._queues.values())

    def __bool__(self) -> bool:
        return len(self) > 0

    def enqueue(
        self,
        instruction: str,
        *,
        lane: str = "default",
        source: str = "runtime",
        metadata: dict[str, Any] | None = None,
    ) -> QueuedInstruction:
        normalized_lane = str(lane or "default").strip() or "default"
        item = QueuedInstruction(
            instruction=str(instruction or "").strip(),
            lane=normalized_lane,
            source=str(source or "runtime").strip() or "runtime",
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )
        queue = self._queues.setdefault(normalized_lane, deque())
        queue.append(item)
        if normalized_lane not in self._lane_order:
            self._lane_order.append(normalized_lane)
        return item

    def append(self, instruction: str) -> QueuedInstruction:
        """List-style compatibility shim for legacy queue callers."""

        return self.enqueue(instruction)

    def pop_next(self) -> QueuedInstruction | None:
        active_lanes = [lane for lane in self._lane_order if self._queues.get(lane)]
        if not active_lanes:
            return None

        start_index = self._round_robin_index % len(active_lanes)
        for offset in range(len(active_lanes)):
            lane = active_lanes[(start_index + offset) % len(active_lanes)]
            queue = self._queues.get(lane)
            if not queue:
                continue
            item = queue.popleft()
            if not queue:
                self._queues.pop(lane, None)
            self._round_robin_index = (start_index + offset + 1) % max(len(active_lanes), 1)
            return item
        return None

    def remove_at(self, index: int) -> QueuedInstruction | None:
        if index < 0:
            return None
        flattened = self.snapshot()
        if index >= len(flattened):
            return None
        target = flattened[index]
        queue = self._queues.get(target.lane)
        if not queue:
            return None
        for item in list(queue):
            if item.queue_id != target.queue_id:
                continue
            queue.remove(item)
            if not queue:
                self._queues.pop(target.lane, None)
            return item
        return None

    def pop(self, index: int = -1) -> str:
        """List-style compatibility shim returning the instruction text."""

        flattened = self.snapshot()
        if not flattened:
            raise IndexError("pop from empty SessionLaneQueue")
        resolved_index = len(flattened) - 1 if index == -1 else index
        item = self.remove_at(resolved_index)
        if item is None:
            raise IndexError("SessionLaneQueue index out of range")
        return item.instruction

    def snapshot(self) -> list[QueuedInstruction]:
        items = [item for queue in self._queues.values() for item in queue]
        return sorted(items, key=lambda item: item.enqueued_at)

    def depth_by_lane(self) -> dict[str, int]:
        return {lane: len(queue) for lane, queue in self._queues.items() if queue}
