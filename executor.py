"""Browser action execution via Playwright."""
import logging
from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes browser actions using Playwright."""

    def __init__(self):
        self.browser: Browser | None = None
        self.page: Page | None = None
        self._playwright = None

    async def initialize(self):
        """Launch browser instance."""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        self.page = await context.new_page()
        logger.info("Browser initialized (1280x720)")

    async def ensure_browser(self):
        if not self.page:
            await self.initialize()

    async def screenshot(self) -> bytes:
        """Capture current page screenshot."""
        await self.ensure_browser()
        return await self.page.screenshot(full_page=False, type="png")

    async def goto(self, url: str) -> dict:
        """Navigate to a URL."""
        await self.ensure_browser()
        response = await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        logger.info(f"Navigated to {url} — status: {response.status if response else 'unknown'}")
        return {"url": self.page.url, "title": await self.page.title()}

    async def click(self, x: int, y: int) -> dict:
        """Click at specific coordinates."""
        await self.ensure_browser()
        await self.page.mouse.click(x, y)
        await self.page.wait_for_timeout(500)
        logger.info(f"Clicked at ({x}, {y})")
        return {"action": "click", "x": x, "y": y, "url": self.page.url}

    async def type_text(self, text: str, x: int = None, y: int = None) -> dict:
        """Type text, optionally clicking a location first."""
        await self.ensure_browser()
        if x is not None and y is not None:
            await self.page.mouse.click(x, y)
            await self.page.wait_for_timeout(200)
        await self.page.keyboard.type(text, delay=50)
        logger.info(f"Typed: {text[:50]}...")
        return {"action": "type", "text": text[:50]}

    async def press_key(self, key: str) -> dict:
        """Press a keyboard key (Enter, Tab, Escape, etc.)."""
        await self.ensure_browser()
        await self.page.keyboard.press(key)
        logger.info(f"Pressed key: {key}")
        return {"action": "press", "key": key}

    async def scroll(self, direction: str = "down", amount: int = 300) -> dict:
        """Scroll the page."""
        await self.ensure_browser()
        delta = amount if direction == "down" else -amount
        await self.page.mouse.wheel(0, delta)
        await self.page.wait_for_timeout(300)
        logger.info(f"Scrolled {direction} by {amount}px")
        return {"action": "scroll", "direction": direction, "amount": amount}

    async def go_back(self) -> dict:
        """Navigate back."""
        await self.ensure_browser()
        await self.page.go_back()
        return {"action": "back", "url": self.page.url}

    async def close(self):
        """Clean up browser resources."""
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
