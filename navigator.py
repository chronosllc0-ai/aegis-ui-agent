"""Navigator agent — exposes browser actions as ADK-compatible tool functions."""
import json
import logging
from src.agent.analyzer import ScreenshotAnalyzer
from src.agent.executor import ActionExecutor

logger = logging.getLogger(__name__)


class NavigatorAgent:
    """Provides tool functions that the ADK agent can call."""

    def __init__(self, analyzer: ScreenshotAnalyzer, executor: ActionExecutor):
        self.analyzer = analyzer
        self.executor = executor

    async def take_screenshot(self) -> str:
        """Capture a screenshot of the current browser state. Call this to see what's on screen."""
        screenshot = await self.executor.screenshot()
        analysis = await self.analyzer.analyze(screenshot)
        return f"Screenshot captured and analyzed:\n{analysis.raw_response}"

    async def analyze_screen(self, task_description: str) -> str:
        """Analyze the current screen with a specific task in mind.
        
        Args:
            task_description: What the user is trying to accomplish.
        """
        screenshot = await self.executor.screenshot()
        analysis = await self.analyzer.analyze(screenshot, task_context=task_description)
        return f"Screen analysis for task '{task_description}':\n{analysis.raw_response}"

    async def go_to_url(self, url: str) -> str:
        """Navigate the browser to a specific URL.
        
        Args:
            url: The full URL to navigate to (e.g., https://www.google.com).
        """
        result = await self.executor.goto(url)
        return f"Navigated to {result['url']} — Page title: {result['title']}"

    async def click_element(self, x: int, y: int, description: str = "") -> str:
        """Click on an element at the specified coordinates.
        
        Args:
            x: X pixel coordinate to click.
            y: Y pixel coordinate to click.
            description: What element you're clicking (for logging).
        """
        result = await self.executor.click(x, y)
        return f"Clicked at ({x}, {y}){f' — {description}' if description else ''}. Current URL: {result['url']}"

    async def type_text(self, text: str, x: int = None, y: int = None) -> str:
        """Type text into the currently focused element or at specific coordinates.
        
        Args:
            text: The text to type.
            x: Optional X coordinate to click before typing.
            y: Optional Y coordinate to click before typing.
        """
        result = await self.executor.type_text(text, x, y)
        return f"Typed: '{result['text']}'"

    async def scroll_page(self, direction: str = "down", amount: int = 300) -> str:
        """Scroll the page up or down.
        
        Args:
            direction: 'up' or 'down'.
            amount: Pixels to scroll (default 300).
        """
        result = await self.executor.scroll(direction, amount)
        return f"Scrolled {direction} by {amount}px"

    async def wait_for_load(self, seconds: float = 2.0) -> str:
        """Wait for the page to finish loading.
        
        Args:
            seconds: Seconds to wait (default 2).
        """
        import asyncio
        await asyncio.sleep(seconds)
        return f"Waited {seconds}s for page load"

    async def go_back(self) -> str:
        """Navigate back to the previous page."""
        result = await self.executor.go_back()
        return f"Went back. Current URL: {result['url']}"
