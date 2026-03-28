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

# Models supported by the Gemini ADK navigator path
SUPPORTED_GEMINI_MODELS = {"gemini-2.5-pro", "gemini-2.5-flash", "gemini-3-pro", "gemini-2.5-pro-preview-03-25"}
# Providers that use the Gemini ADK path
GEMINI_PROVIDERS = {"google", "gemini", ""}


class AgentOrchestrator:
    """Orchestrates the UI navigation pipeline.

    Routing logic:
    - Google / Gemini providers → Google ADK runner (existing path).
    - All other providers (OpenAI, Anthropic, xAI, OpenRouter) →
      UniversalNavigator vision+tool-calling loop.
    """

    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.analyzer = ScreenshotAnalyzer(self.client)
        self.executor = ActionExecutor()
        self.navigator = NavigatorAgent(self.analyzer, self.executor)
        self.session_service = InMemorySessionService()
        self.default_model_name = settings.GEMINI_MODEL
        self.model_name = self.default_model_name
        self.agent: Agent | None = None
        self.mcp_client = MCPClient()

    def _build_agent(self, model_name: str, system_instruction: str | None = None) -> Agent:
        """Build an ADK agent instance for the requested model/instruction."""
        instruction = system_instruction or (
            "You are Aegis, a UI navigation agent. Use tools to navigate webpages and complete the task. "
            "If asked to search the web, go to a search engine, type query, and submit. "
            "When the user's message starts with /plan, treat it as a planning request: "
            "break the task into clear, numbered steps before executing. "
            "List the plan steps first, then execute each step methodically, "
            "reporting progress after each one. The /plan prefix should be stripped "
            "before processing the actual task description."
        )
        return Agent(
            name="aegis_navigator",
            model=model_name,
            description="An AI agent that navigates UIs by seeing screenshots and executing actions.",
            instruction=instruction,
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

    async def _apply_session_settings(self, session_settings: dict[str, Any] | None) -> None:
        """Apply per-session settings before executing a Gemini ADK task."""
        if not session_settings:
            return

        requested_model = str(session_settings.get("model", self.model_name)).strip() or self.model_name
        if requested_model not in SUPPORTED_GEMINI_MODELS:
            requested_model = self.model_name
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

    async def _resolve_session_agent(self, session_settings: dict[str, Any] | None) -> tuple[Agent, str]:
        """Return the ADK agent instance to use for the current Gemini session."""
        if self.agent is None:
            await self.initialize()
        assert self.agent is not None
        return self.agent, self.model_name

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

    async def _resolve_provider_for_navigation(
        self,
        session_settings: dict[str, Any] | None,
        user_uid: str | None,
    ) -> tuple[str, Any, str] | None:
        """Resolve provider name, instance, and model for non-Gemini navigation.

        Returns (provider_name, provider_instance, model_id) or None if
        the provider cannot be resolved (missing key → error handled by caller).
        """
        if not session_settings:
            return None
        provider_name = str(session_settings.get("provider", "")).strip().lower()
        if not provider_name or provider_name in GEMINI_PROVIDERS:
            return None

        model_id = str(session_settings.get("model", "")).strip()

        # Try to get the user's stored BYOK key first
        api_key: str | None = None
        if user_uid:
            try:
                from backend.database import get_session as _get_session
                from backend.key_management import KeyManager
                _km = KeyManager(settings.ENCRYPTION_SECRET)
                async for db_session in _get_session():
                    api_key = await _km.get_key(db_session, user_uid, provider_name)
                    break
            except Exception:  # noqa: BLE001
                logger.debug("Could not retrieve BYOK key for %s/%s", user_uid, provider_name)

        # Fall back to server-side env key
        if not api_key:
            env_keys: dict[str, str] = {
                "openai": settings.OPENAI_API_KEY,
                "anthropic": settings.ANTHROPIC_API_KEY,
                "xai": settings.XAI_API_KEY,
                "openrouter": settings.OPENROUTER_API_KEY,
            }
            api_key = env_keys.get(provider_name, "").strip()

        if not api_key:
            return None  # caller will surface a missing-key error

        from backend.providers import get_provider
        provider_instance = get_provider(provider_name, api_key, default_model=model_id or None)
        return provider_name, provider_instance, model_id

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
        user_uid: str | None = None,
    ) -> dict[str, Any]:
        """Execute a UI navigation task from a natural language instruction.

        Automatically routes to the Gemini ADK path or the universal
        vision+tool-calling navigator depending on the requested provider.
        """
        provider_name = str((settings or {}).get("provider", "")).strip().lower()
        is_gemini_path = not provider_name or provider_name in GEMINI_PROVIDERS

        # ── Non-Gemini path ────────────────────────────────────────────
        if not is_gemini_path:
            resolved = await self._resolve_provider_for_navigation(settings, user_uid)
            if resolved is None:
                # No API key available — surface a clear error
                missing_key_msg = (
                    f"No API key found for provider '{provider_name}'. "
                    "Please add your key in Settings → API Keys, or set a server-side environment variable."
                )
                if on_step:
                    await on_step({"type": "error", "content": missing_key_msg, "steering": []})
                return {"status": "failed", "instruction": instruction, "error": missing_key_msg}

            _, provider_instance, model_id = resolved
            logger.info("Using universal navigator for provider=%s model=%s", provider_name, model_id)

            from universal_navigator import run_universal_navigation
            return await run_universal_navigation(
                provider=provider_instance,
                model=model_id,
                executor=self.executor,
                instruction=instruction,
                on_step=on_step,
                on_frame=on_frame,
                cancel_event=cancel_event,
                steering_context=steering_context,
                on_workflow_step=on_workflow_step,
            )

        # ── Gemini / ADK path (original) ───────────────────────────────
        if self.agent is None:
            await self.initialize()
        await self._apply_session_settings(settings)
        assert self.agent is not None

        session_agent, _ = await self._resolve_session_agent(settings)

        runner = Runner(agent=session_agent, app_name="aegis", session_service=self.session_service)
        user_id = session_id
        await self.session_service.create_session(app_name="aegis", user_id=user_id, session_id=session_id)

        steps: list[dict[str, Any]] = []
        parent_step_id: str | None = None

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
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
