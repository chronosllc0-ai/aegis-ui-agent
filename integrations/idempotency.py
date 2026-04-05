"""Helpers for bounded webhook delivery idempotency tracking."""

from __future__ import annotations

from collections import deque


class DeliveryDeduper:
    """Bounded in-memory deduper for webhook/event delivery IDs."""

    def __init__(self, max_entries: int = 10_000) -> None:
        self._max_entries = max_entries
        self._seen: set[str] = set()
        self._order: deque[str] = deque()

    def seen_or_add(self, delivery_id: str) -> bool:
        """Return True if already seen; otherwise store it and return False."""
        if not delivery_id:
            return False
        if delivery_id in self._seen:
            return True

        self._seen.add(delivery_id)
        self._order.append(delivery_id)
        while len(self._order) > self._max_entries:
            oldest = self._order.popleft()
            self._seen.discard(oldest)
        return False

    def clear(self) -> None:
        """Reset deduper state."""
        self._seen.clear()
        self._order.clear()
