"""PydanticAI-native runtime for non-Gemini providers with universal fallback."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
from contextlib import suppress
import json
import logging
from typing import Any

from backend.providers.base import BaseProvider
from executor import ActionExecutor
from universal_navigator import UniversalToolExecutor, _available_tools, run_universal_navigation

logger = logging.getLogger(__name__)


def _build_pydantic_model(provider: BaseProvider, model_name: str) -> Any:
    """Build a PydanticAI model instance from the active provider adapter."""
    provider_name = str(getattr(provider, "provider_name", "")).strip().lower()
    api_key = str(getattr(provider, "api_key", "")).strip() or None
    default_model = str(getattr(provider, "default_model", "")).strip()
    selected_model = model_name or default_model

    if provider_name == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(selected_model, provider=OpenAIProvider(api_key=api_key))
    if provider_name == "openrouter":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(
            selected_model,
            provider=OpenAIProvider(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
            ),
        )
    if provider_name == "fireworks":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(
            selected_model,
            provider=OpenAIProvider(
                api_key=api_key,
                base_url="https://api.fireworks.ai/inference/v1",
            ),
        )
    if provider_name == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(selected_model, provider=AnthropicProvider(api_key=api_key))
    if provider_name == "groq":
        from pydantic_ai.models.groq import GroqModel
        from pydantic_ai.providers.groq import GroqProvider

        return GroqModel(selected_model, provider=GroqProvider(api_key=api_key))
    if provider_name == "mistral":
        from pydantic_ai.models.mistral import MistralModel
        from pydantic_ai.providers.mistral import MistralProvider

        return MistralModel(selected_model, provider=MistralProvider(api_key=api_key))
    if provider_name == "xai":
        from pydantic_ai.models.xai import XaiModel
        from pydantic_ai.providers.xai import XaiProvider

        return XaiModel(selected_model, provider=XaiProvider(api_key=api_key))

    raise ValueError(f"Unsupported non-Gemini provider for PydanticAI runtime: {provider_name}")


async def run_pydantic_adk_navigation(
    *,
    provider: BaseProvider,
    model: str,
    executor: ActionExecutor,
    session_id: str,
    instruction: str,
    settings: dict[str, Any],
    on_step: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    on_frame: Callable[[str], Awaitable[None]] | None = None,
    cancel_event: Any = None,
    steering_context: list[str] | None = None,
    on_workflow_step: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    on_user_input: Callable[[str, list[str]], Awaitable[str]] | None = None,
    user_uid: str | None = None,
    enable_reasoning: bool = False,
    reasoning_effort: str = "medium",
    on_reasoning_delta: Callable[[str, str], Awaitable[None]] | None = None,
    on_spawn_subagent: Callable[[str, str], Awaitable[str]] | None = None,
    on_message_subagent: Callable[[str, str], Awaitable[bool]] | None = None,
    is_subagent: bool = False,
) -> dict[str, Any]:
    """Execute non-Gemini navigation with PydanticAI; fall back to universal runtime on errors."""
    try:
        from pydantic_ai import Agent
    except ImportError as exc:
        logger.warning("pydantic_ai unavailable; using universal fallback: %s", exc)
        return await run_universal_navigation(
            provider=provider,
            model=model,
            executor=executor,
            session_id=session_id,
            instruction=instruction,
            settings=settings,
            on_step=on_step,
            on_frame=on_frame,
            cancel_event=cancel_event,
            steering_context=steering_context,
            on_workflow_step=on_workflow_step,
            on_user_input=on_user_input,
            user_uid=user_uid,
            enable_reasoning=enable_reasoning,
            reasoning_effort=reasoning_effort,
            on_reasoning_delta=on_reasoning_delta,
            on_spawn_subagent=on_spawn_subagent,
            on_message_subagent=on_message_subagent,
            is_subagent=is_subagent,
        )

    try:
        pyd_model = _build_pydantic_model(provider, model)
        tool_executor = UniversalToolExecutor(
            executor,
            session_id=session_id,
            settings=settings,
            user_uid=user_uid,
            on_user_input=on_user_input,
            on_spawn_subagent=on_spawn_subagent,
            on_message_subagent=on_message_subagent,
            is_subagent=is_subagent,
        )

        available_tool_names = [t["name"] for t in _available_tools(settings, is_subagent=is_subagent)]
        if on_step is not None:
            await on_step(
                {
                    "type": "message",
                    "content": "Using non-Gemini PydanticAI ADK runtime.",
                    "steering": [],
                }
            )

        agent = Agent(
            model=pyd_model,
            system_prompt=(
                "You are Aegis non-Gemini runtime. Use the `run_tool` function for every action. "
                "When complete, call `finish_task`. If blocked, call `fail_task`."
            ),
            retries=1,
        )

        @agent.tool_plain(name="run_tool")
        async def run_tool(tool: str, args_json: str = "{}") -> str:
            payload = json.loads(args_json) if args_json.strip() else {}
            if not isinstance(payload, dict):
                return "run_tool error: args_json must decode to an object."
            tool_call = {**payload, "tool": tool}
            if on_step is not None:
                await on_step({"type": "tool-call", "content": json.dumps(tool_call), "steering": []})
            result_text, image_bytes = await tool_executor.run(tool_call)
            if image_bytes and on_frame is not None:
                await on_frame(base64.b64encode(image_bytes).decode())
            return result_text

        @agent.tool_plain(name="finish_task")
        async def finish_task(summary: str = "Task completed.") -> str:
            return f"done::{summary}"

        @agent.tool_plain(name="fail_task")
        async def fail_task(reason: str) -> str:
            return f"failed::{reason}"

        steering_notes = "; ".join(steering_context or [])
        prompt = (
            f"Task: {instruction}\n"
            f"Available tools: {', '.join(available_tool_names)}\n"
            "For each tool call, use run_tool(tool, args_json) where args_json is strict JSON.\n"
            "Terminate with finish_task(summary) or fail_task(reason).\n"
        )
        if steering_notes:
            prompt += f"Steering notes: {steering_notes}\n"

        if cancel_event is not None:
            run_task = asyncio.create_task(agent.run(prompt))
            cancel_task = asyncio.create_task(cancel_event.wait())
            try:
                done, _ = await asyncio.wait(
                    {run_task, cancel_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancel_task in done and cancel_event.is_set():
                    run_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await run_task
                    raise asyncio.CancelledError
                run_result = await run_task
            finally:
                cancel_task.cancel()
                with suppress(asyncio.CancelledError):
                    await cancel_task
        else:
            run_result = await agent.run(prompt)
        output = str(run_result.output)

        if output.startswith("failed::"):
            reason = output.split("::", 1)[1].strip() or "Unknown failure."
            if on_step is not None:
                await on_step({"type": "error", "content": reason, "steering": []})
            return {"status": "failed", "instruction": instruction, "error": reason, "steps": []}

        summary = output.split("::", 1)[1].strip() if output.startswith("done::") else output.strip()
        if on_step is not None:
            await on_step({"type": "result", "content": summary or "Task completed.", "steering": []})
        return {"status": "completed", "instruction": instruction, "summary": summary, "steps": []}
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("PydanticAI runtime failed; falling back to universal navigator")
        if on_step is not None:
            await on_step(
                {
                    "type": "message",
                    "content": f"PydanticAI runtime failed ({exc}); using fallback runtime.",
                    "steering": [],
                }
            )
        return await run_universal_navigation(
            provider=provider,
            model=model,
            executor=executor,
            session_id=session_id,
            instruction=instruction,
            settings=settings,
            on_step=on_step,
            on_frame=on_frame,
            cancel_event=cancel_event,
            steering_context=steering_context,
            on_workflow_step=on_workflow_step,
            on_user_input=on_user_input,
            user_uid=user_uid,
            enable_reasoning=enable_reasoning,
            reasoning_effort=reasoning_effort,
            on_reasoning_delta=on_reasoning_delta,
            on_spawn_subagent=on_spawn_subagent,
            on_message_subagent=on_message_subagent,
            is_subagent=is_subagent,
        )
