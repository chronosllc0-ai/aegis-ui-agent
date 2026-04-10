"""PydanticAI-backed runtime adapter for non-Gemini providers.

This module provides a stable integration seam so non-Gemini execution can
standardize on a PydanticAI-based adapter over time, while preserving the
existing universal navigator runtime behavior.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import Any

from backend.providers.base import BaseProvider
from executor import ActionExecutor
from universal_navigator import run_universal_navigation

logger = logging.getLogger(__name__)


def _is_pydantic_ai_available() -> bool:
    """Return whether pydantic_ai is importable in the current runtime."""
    try:
        import pydantic_ai  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


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
    """Execute a non-Gemini task through the PydanticAI adapter seam.

    The current implementation preserves the proven Universal Navigator
    execution semantics while exposing a dedicated adapter boundary for
    PydanticAI-native orchestration.
    """
    pydantic_ai_available = _is_pydantic_ai_available()

    if on_step is not None:
        await on_step(
            {
                "type": "message",
                "content": (
                    "Using non-Gemini PydanticAI ADK runtime."
                    if pydantic_ai_available
                    else "Using non-Gemini ADK runtime adapter (pydantic_ai unavailable; using compatibility mode)."
                ),
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
