"""Browser action execution via Playwright."""

from __future__ import annotations

from typing import Any
import logging

from playwright.async_api import Browser, Error, Page, Playwright, async_playwright

from config import settings

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes browser actions using Playwright."""

    def __init__(self) -> None:
        self.browser: Browser | None = None
        self.page: Page | None = None
        self._playwright: Playwright | None = None

    async def initialize(self) -> None:
        """Launch browser and initialize a page context."""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=settings.BROWSER_HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await self.browser.new_context(
            viewport={"width": settings.VIEWPORT_WIDTH, "height": settings.VIEWPORT_HEIGHT},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        self.page = await context.new_page()
        logger.info("Browser initialized (%sx%s)", settings.VIEWPORT_WIDTH, settings.VIEWPORT_HEIGHT)

    async def ensure_browser(self) -> None:
        """Ensure browser resources are initialized before action execution."""
        if self.page is None:
            await self.initialize()

    async def screenshot(self) -> bytes:
        """Capture the current viewport as PNG bytes."""
        await self.ensure_browser()
        assert self.page is not None
        return await self.page.screenshot(full_page=False, type="png")

    async def goto(self, url: str) -> dict[str, Any]:
        """Navigate to a URL and return page metadata."""
        await self.ensure_browser()
        assert self.page is not None
        response = await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        status = response.status if response else None
        logger.info("Navigated to %s status=%s", url, status)
        return {"url": self.page.url, "title": await self.page.title(), "status": status}

    async def click(self, x: int, y: int) -> dict[str, Any]:
        """Click coordinates and return basic action metadata."""
        await self.ensure_browser()
        assert self.page is not None
        await self.page.mouse.click(x, y)
        await self.page.wait_for_timeout(500)
        logger.info("Clicked at (%s,%s)", x, y)
        return {"action": "click", "x": x, "y": y, "url": self.page.url}

    async def type_text(self, text: str, x: int | None = None, y: int | None = None) -> dict[str, Any]:
        """Type text into focused element; optionally click coordinates first."""
        await self.ensure_browser()
        assert self.page is not None
        if x is not None and y is not None:
            await self.page.mouse.click(x, y)
            await self.page.wait_for_timeout(200)
        await self.page.keyboard.type(text, delay=35)
        logger.info("Typed text length=%s", len(text))
        return {"action": "type", "text": text, "url": self.page.url}

    async def press_key(self, key: str) -> dict[str, Any]:
        """Press a keyboard key (Enter, Tab, Escape, etc.)."""
        await self.ensure_browser()
        assert self.page is not None
        await self.page.keyboard.press(key)
        logger.info("Pressed key %s", key)
        return {"action": "press", "key": key, "url": self.page.url}

    async def scroll(self, direction: str = "down", amount: int = 300) -> dict[str, Any]:
        """Scroll the page in pixels."""
        await self.ensure_browser()
        assert self.page is not None
        delta = amount if direction == "down" else -amount
        await self.page.mouse.wheel(0, delta)
        await self.page.wait_for_timeout(300)
        logger.info("Scrolled %s by %s", direction, amount)
        return {"action": "scroll", "direction": direction, "amount": amount, "url": self.page.url}

    async def go_back(self) -> dict[str, Any]:
        """Navigate browser history backward by one entry."""
        await self.ensure_browser()
        assert self.page is not None
        try:
            await self.page.go_back(wait_until="domcontentloaded")
        except Error as exc:
            logger.warning("go_back failed: %s", exc)
        return {"action": "back", "url": self.page.url}

    async def close(self) -> None:
        """Clean up browser resources."""
        if self.browser is not None:
            await self.browser.close()
            self.browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self.page = None
