"""ADK-based agent orchestrator for UI navigation tasks."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
import logging
from typing import Any
from uuid import uuid4

from google import genai
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from analyzer import ScreenshotAnalyzer, detect_available_model
from config import settings
from executor import ActionExecutor
from mcp_client import MCPClient
from navigator import NavigatorAgent

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Orchestrates the UI navigation pipeline using ADK."""

    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY or "test-key")
        self.analyzer = ScreenshotAnalyzer(self.client)
        self.executor = ActionExecutor()
        self.navigator = NavigatorAgent(self.analyzer, self.executor)
        self.session_service = InMemorySessionService()
        self.model_name = settings.GEMINI_MODEL
        self.agent: Agent | None = None
        self.mcp_client = MCPClient()

    async def initialize(self) -> None:
        """Initialize model selection and ADK agent instance."""
        key = settings.GEMINI_API_KEY.strip()
        has_real_key = bool(key) and "your-gemini" not in key.lower()
        if has_real_key:
            self.model_name = await detect_available_model(self.client)
        self.analyzer.model = self.model_name
        self.agent = Agent(
            name="aegis_navigator",
            model=self.model_name,
            description="An AI agent that navigates UIs by seeing screenshots and executing actions.",
            instruction=(
                "You are Aegis, a UI navigation agent. Use tools to navigate webpages and complete the task. "
                "If asked to search the web, go to a search engine, type query, and submit."
            ),
            tools=[
                self.navigator.take_screenshot,
                self.navigator.analyze_screen,
                self.navigator.click_element,
                self.navigator.type_text,
                self.navigator.scroll_page,
                self.navigator.go_to_url,
                self.navigator.wait_for_load,
                self.navigator.go_back,
            ],
        )
        logger.info("Orchestrator initialized with model %s", self.model_name)

    async def capture_frame_b64(self) -> str:
        """Capture the current browser viewport as base64 PNG data."""
        screenshot = await self.executor.screenshot()
        return base64.b64encode(screenshot).decode("utf-8")

    async def execute_task(
        self,
        session_id: str,
        instruction: str,
        on_step: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        on_frame: Callable[[str], Awaitable[None]] | None = None,
        cancel_event: asyncio.Event | None = None,
        steering_context: list[str] | None = None,
        settings: dict[str, Any] | None = None,
        on_workflow_step: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """Execute a UI navigation task from a natural language instruction."""
        if self.agent is None:
            await self.initialize()
        assert self.agent is not None

        runner = Runner(agent=self.agent, app_name="aegis", session_service=self.session_service)
        await self.session_service.create_session(app_name="aegis", user_id="user", session_id=session_id)

        steps: list[dict[str, Any]] = []
        parent_step_id: str | None = None
        if on_frame is not None:
            await on_frame(await self.capture_frame_b64())

        async for event in runner.run_async(user_id="user", session_id=session_id, new_message=instruction):
            if cancel_event is not None and cancel_event.is_set():
                logger.info("Task cancelled for session %s", session_id)
                return {"status": "interrupted", "instruction": instruction, "steps": steps}

            injected = []
            if steering_context:
                injected = steering_context.copy()
                steering_context.clear()

            step_data = {
                "type": str(getattr(event, "type", "unknown")),
                "content": str(getattr(event, "content", "")) if getattr(event, "content", None) else None,
                "steering": injected,
            }
            steps.append(step_data)
            workflow_step = {
                "step_id": str(uuid4()),
                "parent_step_id": parent_step_id,
                "action": step_data["type"],
                "description": step_data.get("content") or "Agent step",
                "status": "completed",
                "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
                "duration_ms": 500,
                "screenshot": None,
            }
            parent_step_id = workflow_step["step_id"]
            if on_step is not None:
                await on_step(step_data)
            if on_workflow_step is not None:
                await on_workflow_step(workflow_step)
            if on_frame is not None:
                await on_frame(await self.capture_frame_b64())

        return {"status": "completed", "instruction": instruction, "steps": steps}
