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
# pydantic_adk_runner removed — universal_navigator handles all providers
from universal_navigator import run_universal_navigation
from config import settings as settings_module
from executor import ActionExecutor
from navigator import NavigatorAgent

logger = logging.getLogger(__name__)
# Backward-compatible alias used by existing tests/importers.
settings = settings_module

# Models supported by the Gemini ADK navigator path
SUPPORTED_GEMINI_MODELS = {"gemini-2.5-pro", "gemini-2.5-flash", "gemini-3-pro", "gemini-2.5-pro-preview-03-25"}
# Providers that use the Gemini ADK path
GEMINI_PROVIDERS = {"google", "gemini", ""}

PROVIDER_ALIASES: dict[str, str] = {
    "google": "google",
    "gemini": "google",
    "google gemini": "google",
    "google (gemini)": "google",
    "chronos": "chronos",
    "chronos gateway": "chronos",
    "chronos ai": "chronos",
    "gateway": "chronos",
    "openai": "openai",
    "anthropic": "anthropic",
    "xai": "xai",
    "x.ai": "xai",
    "openrouter": "openrouter",
    "fireworks": "fireworks",
    "fireworks ai": "fireworks",
}


def _normalize_provider_name(provider_name: str, model_id: str = "") -> str:
    """Normalize provider labels/aliases from UI payloads into canonical IDs."""
    candidate = provider_name.strip().lower().replace("-", " ")
    if candidate in PROVIDER_ALIASES:
        return PROVIDER_ALIASES[candidate]

    compact = candidate.replace(" ", "")
    if compact in {"fireworksai", "chronosgateway"}:
        return "fireworks" if compact == "fireworksai" else "chronos"

    normalized_model = model_id.strip().lower()
    if normalized_model.startswith("accounts/fireworks/models/"):
        return "fireworks"
    if normalized_model.startswith("gemini"):
        return "google"
    return candidate


class AgentOrchestrator:
    """Orchestrates the UI navigation pipeline.

    Routing logic:
    - Google / Gemini providers → Google ADK runner (existing path).
    - All other providers (OpenAI, Anthropic, xAI, OpenRouter) →
      UniversalNavigator vision+tool-calling loop.
    """

    def __init__(self) -> None:
        self.executor = ActionExecutor()
        self.client: genai.Client | None = None
        self.analyzer: ScreenshotAnalyzer | None = None
        self.navigator: NavigatorAgent | None = None
        self.session_service = InMemorySessionService()
        self.default_model_name = settings_module.GEMINI_MODEL
        self.model_name = self.default_model_name
        self.agent: Agent | None = None

    def _ensure_gemini_stack(self) -> None:
        """Initialize Gemini-dependent components lazily when needed."""
        if self.client is None:
            self.client = genai.Client(api_key=settings_module.GEMINI_API_KEY)
        if self.analyzer is None:
            self.analyzer = ScreenshotAnalyzer(self.client)
        if self.navigator is None:
            self.navigator = NavigatorAgent(self.analyzer, self.executor)

    def _build_agent(self, model_name: str, system_instruction: str | None = None) -> Agent:
        """Build an ADK agent instance for the requested model/instruction."""
        instruction = system_instruction or (
            "You are Aegis, an autonomous AI agent built by Chronos AI. "
            "You have browser tools for web UI interaction. Analyze each task and decide the best approach. "
            "Use browser tools only when the task requires interacting with a web UI — "
            "do not take a screenshot as a default first step. "
            "When the user's message starts with /plan, break the task into clear numbered steps first, "
            "then execute each step methodically. Strip the /plan prefix before processing."
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
            if self.analyzer is not None:
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
        self._ensure_gemini_stack()
        assert self.client is not None
        assert self.analyzer is not None
        key = settings_module.GEMINI_API_KEY.strip()
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

        # ── Chronos Gateway — route via platform OpenRouter key ───────
        CHRONOS_GATEWAY = "chronos"
        if provider_name == CHRONOS_GATEWAY:
            api_key = settings_module.OPENROUTER_API_KEY.strip()
            if not api_key:
                return None  # no platform key configured
            from backend.providers import get_provider
            # Preserve explicit model slugs (including ':free') so execution and
            # credit accounting refer to the same exact model identifier.
            provider_instance = get_provider("openrouter", api_key, default_model=model_id or "nvidia/nemotron-3-super-120b-a12b:free")
            return "chronos", provider_instance, model_id

        # Try to get the user's stored BYOK key first
        api_key: str | None = None
        if user_uid:
            try:
                from backend.database import get_session as _get_session
                from backend.key_management import KeyManager
                _km = KeyManager(settings_module.ENCRYPTION_SECRET)
                async for db_session in _get_session():
                    api_key = await _km.get_key(db_session, user_uid, provider_name)
                    break
            except Exception:  # noqa: BLE001
                logger.debug("Could not retrieve BYOK key for %s/%s", user_uid, provider_name)

        # Fall back to server-side env key
        if not api_key:
            env_keys: dict[str, str] = {
                "openai": settings_module.OPENAI_API_KEY,
                "anthropic": settings_module.ANTHROPIC_API_KEY,
                "xai": settings_module.XAI_API_KEY,
                "openrouter": settings_module.OPENROUTER_API_KEY,
                "fireworks": settings_module.FIREWORKS_API_KEY,
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
        session_settings: dict[str, Any] | None = None,
        on_workflow_step: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        user_uid: str | None = None,
        on_user_input: Callable[[str, list[str]], Awaitable[str]] | None = None,
        on_handoff_to_user: Callable[[str, str, str | None, str], Awaitable[str]] | None = None,
        on_reasoning_delta: Callable[[str, str], Awaitable[None]] | None = None,
        on_spawn_subagent: Callable[[str, str], Awaitable[str]] | None = None,
        on_message_subagent: Callable[[str, str], Awaitable[bool]] | None = None,
        on_first_model_call: Callable[[str, str], Awaitable[None]] | None = None,
        is_subagent: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute a UI navigation task from a natural language instruction.

        Automatically routes to the Gemini ADK path or the universal
        vision+tool-calling navigator depending on the requested provider.
        """
        legacy_settings = kwargs.pop("settings", None)
        if kwargs:
            logger.debug("Unused execute_task kwargs: %s", sorted(kwargs.keys()))
        resolved_session_settings = session_settings if session_settings is not None else legacy_settings
        session_settings = resolved_session_settings if isinstance(resolved_session_settings, dict) else {}
        model_id = str(session_settings.get("model", "")).strip()
        raw_provider = str(session_settings.get("provider", "")).strip()
        provider_name = _normalize_provider_name(raw_provider, model_id)
        if not provider_name:
            provider_name = "chronos"
        is_gemini_path = not provider_name or provider_name in GEMINI_PROVIDERS

        # ── Non-Gemini path ────────────────────────────────────────────
        if not is_gemini_path:
            resolved = await self._resolve_provider_for_navigation({**session_settings, "provider": provider_name}, user_uid)
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
            logger.info("Using universal agent runner for provider=%s model=%s", provider_name, model_id)

            enable_reasoning = bool(session_settings.get("enable_reasoning", False))
            reasoning_effort = str(session_settings.get("reasoning_effort", "medium"))

            # Route directly through the universal agent runner — bypasses the PydanticAI shim
            # which had inferior tool schema exposure and leaked internal runtime messages to chat.
            return await run_universal_navigation(
                provider=provider_instance,
                model=model_id,
                executor=self.executor,
                session_id=session_id,
                instruction=instruction,
                settings=session_settings,
                on_step=on_step,
                on_frame=on_frame,
                cancel_event=cancel_event,
                steering_context=steering_context,
                on_workflow_step=on_workflow_step,
                on_user_input=on_user_input,
                on_handoff_to_user=on_handoff_to_user,
                user_uid=user_uid,
                enable_reasoning=enable_reasoning,
                reasoning_effort=reasoning_effort,
                on_reasoning_delta=on_reasoning_delta,
                on_spawn_subagent=on_spawn_subagent,
                on_message_subagent=on_message_subagent,
                on_first_model_call=on_first_model_call,
                is_subagent=is_subagent,
            )

        # ── Gemini / ADK path (original) ───────────────────────────────
        # Verify we have a working Gemini API key before attempting ADK
        gemini_key = settings_module.GEMINI_API_KEY.strip()
        has_real_gemini_key = bool(gemini_key) and "your-gemini" not in gemini_key.lower()
        if not has_real_gemini_key:
            missing_key_msg = (
                "No Gemini API key configured on the server. "
                "To use Google (Gemini) provider, add your GEMINI_API_KEY in Settings → API Keys "
                "or switch to Chronos Gateway which works out of the box."
            )
            if on_step:
                await on_step({"type": "error", "content": missing_key_msg, "steering": []})
            return {"status": "failed", "instruction": instruction, "error": missing_key_msg}

        if self.agent is None:
            await self.initialize()
        await self._apply_session_settings(session_settings)
        assert self.agent is not None

        session_agent, _ = await self._resolve_session_agent(session_settings)

        runner = Runner(agent=session_agent, app_name="aegis", session_service=self.session_service)
        user_id = session_id
        await self.session_service.create_session(app_name="aegis", user_id=user_id, session_id=session_id)

        steps: list[dict[str, Any]] = []
        parent_step_id: str | None = None

        try:
            if on_first_model_call is not None:
                await on_first_model_call(model_id or "gemini-2.5-pro", "google")
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

        except Exception as adk_exc:  # noqa: BLE001
            # Translate common ADK / Gemini API errors into actionable messages
            exc_str = str(adk_exc).lower()
            if "401" in exc_str or "api key" in exc_str or "invalid" in exc_str or "unauthorized" in exc_str:
                readable_error = (
                    "Gemini API key is invalid or expired. "
                    "Please check your GEMINI_API_KEY, or switch to Chronos Gateway in Settings."
                )
            elif "429" in exc_str or "quota" in exc_str or "resource exhausted" in exc_str:
                readable_error = (
                    "Gemini API quota exceeded or rate-limited. "
                    "Please wait a moment and try again, or switch to Chronos Gateway."
                )
            elif "403" in exc_str or "permission" in exc_str or "forbidden" in exc_str:
                readable_error = (
                    "Gemini API access denied (403). "
                    "Check that your API key has the correct permissions."
                )
            else:
                readable_error = f"Gemini agent error: {adk_exc}"
            logger.exception("Gemini ADK runner failed for session %s", session_id)
            raise RuntimeError(readable_error) from adk_exc

        return {"status": "completed", "instruction": instruction, "steps": steps}
