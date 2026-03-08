"""Navigator agent tools bridging analyzer and executor."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import logging

from analyzer import ScreenshotAnalyzer
from executor import ActionExecutor

logger = logging.getLogger(__name__)


class NavigatorAgent:
    """Provides tool functions that the ADK agent can call."""

    def __init__(self, analyzer: ScreenshotAnalyzer, executor: ActionExecutor) -> None:
        self.analyzer = analyzer
        self.executor = executor

    async def take_screenshot(self) -> str:
        """Capture a screenshot and return a compact structured summary."""
        screenshot = await self.executor.screenshot()
        analysis = await self.analyzer.analyze(screenshot)
        return f"page_type={analysis.page_type}; elements={len(analysis.elements)}"

    async def analyze_screen(self, task_description: str) -> str:
        """Analyze the current screen for the given task description."""
        screenshot = await self.executor.screenshot()
        analysis = await self.analyzer.analyze(screenshot, task_context=task_description)
        return str(
            {
                "page_type": analysis.page_type,
                "elements": [asdict(element) for element in analysis.elements],
                "current_state": analysis.current_state,
                "navigation_context": analysis.navigation_context,
            }
        )

    async def go_to_url(self, url: str) -> str:
        """Navigate the browser to the specified URL."""
        result = await self.executor.goto(url)
        return f"Navigated to {result['url']} ({result['title']})"

    async def click_element(self, x: int, y: int, description: str = "") -> str:
        """Click an element at coordinates."""
        result = await self.executor.click(x, y)
        suffix = f" ({description})" if description else ""
        return f"Clicked {x},{y}{suffix}; url={result['url']}"

    async def type_text(self, text: str, x: int | None = None, y: int | None = None) -> str:
        """Type text into the page with optional pre-click coordinates."""
        await self.executor.type_text(text, x, y)
        return f"Typed {len(text)} chars"

    async def scroll_page(self, direction: str = "down", amount: int = 300) -> str:
        """Scroll page up or down by amount."""
        await self.executor.scroll(direction, amount)
        return f"Scrolled {direction} by {amount}"

    async def wait_for_load(self, seconds: float = 1.5) -> str:
        """Wait briefly to let asynchronous page changes settle."""
        await asyncio.sleep(seconds)
        return f"Waited {seconds:.1f}s"

    async def go_back(self) -> str:
        """Navigate back one browser history entry."""
        result = await self.executor.go_back()
        return f"Back to {result['url']}"
