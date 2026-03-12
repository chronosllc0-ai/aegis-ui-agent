"""ADK-based agent orchestrator for UI navigation tasks."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
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
SUPPORTED_SESSION_MODELS = {"gemini-2.5-pro", "gemini-2.5-flash", "gemini-3-pro", "gemini-2.5-pro-preview-03-25"}


class AgentOrchestrator:
    """Orchestrates the UI navigation pipeline using ADK."""

    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY or "test-key")
        self.executor = ActionExecutor()
        self.session_service = InMemorySessionService()
        self.default_model_name = settings.GEMINI_MODEL
        self.agent: Agent | None = None
        self.mcp_client = MCPClient()


    def _build_agent(self, model_name: str, system_instruction: str | None = None) -> Agent:
        """Build an ADK agent instance for the requested model/instruction."""
        instruction = system_instruction or (
            "You are Aegis, a UI navigation agent. Use tools to navigate webpages and complete the task. "
            "If asked to search the web, go to a search engine, type query, and submit."
        )
        return Agent(
            name="aegis_navigator",
            model=model_name,
            description="An AI agent that navigates UIs by seeing screenshots and executing actions.",
            instruction=instruction,
            tools=[
                navigator.take_screenshot,
                navigator.analyze_screen,
                navigator.click_element,
                navigator.type_text,
                navigator.scroll_page,
                navigator.go_to_url,
                navigator.wait_for_load,
                navigator.go_back,
            ],
        )

    async def _apply_session_settings(self, session_settings: dict[str, Any] | None) -> None:
        """Apply per-session settings before executing a task."""
        if not session_settings:
            return

        requested_model = str(session_settings.get("model", self.model_name)).strip() or self.model_name
        system_instruction = session_settings.get("system_instruction")

        should_rebuild = self.agent is None
        if requested_model != self.model_name:
            self.model_name = requested_model
            self.analyzer.model = self.model_name
            should_rebuild = True

        if isinstance(system_instruction, str) and system_instruction.strip():
            should_rebuild = True

        if should_rebuild:
            self.agent = self._build_agent(self.model_name, system_instruction if isinstance(system_instruction, str) else None)
            logger.info("Applied session settings", extra={"model": self.model_name, "has_system_instruction": bool(system_instruction)})
    async def initialize(self) -> None:
        """Initialize model selection and ADK agent instance."""
        key = settings.GEMINI_API_KEY.strip()
        has_real_key = bool(key) and "your-gemini" not in key.lower()
        if has_real_key:
            self.model_name = await detect_available_model(self.client)
        self.analyzer.model = self.model_name
        self.agent = self._build_agent(self.model_name)
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
        await self._apply_session_settings(settings)
        assert self.agent is not None
.

        session_agent, _ = await self._resolve_session_agent(settings)

        runner = Runner(agent=session_agent, app_name="aegis", session_service=self.session_service)
        await self.session_service.create_session(app_name="aegis", user_id="user", session_id=session_id)

        steps: list[dict[str, Any]] = []
        parent_step_id: str | None = None
        if on_frame is not None:
            await on_frame(await self.capture_frame_b64())

        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=instruction):
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
