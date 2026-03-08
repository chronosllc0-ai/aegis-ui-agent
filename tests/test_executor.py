"""Tests for executor behavior."""

from __future__ import annotations

import asyncio

from executor import ActionExecutor


class _FakePage:
    async def screenshot(self, full_page: bool, type: str) -> bytes:
        _ = full_page
        _ = type
        return b"\x89PNG\r\n\x1a\nFAKEPNG"


def test_screenshot_returns_png_bytes() -> None:
    """Executor screenshot should return bytes with PNG header."""
    executor = ActionExecutor()
    executor.page = _FakePage()  # type: ignore[assignment]
    data = asyncio.run(executor.screenshot())
    assert isinstance(data, bytes)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
