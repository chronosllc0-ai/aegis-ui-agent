"""Node-level orchestrator routing for specialist agent modes."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Final

from backend.modes import AgentMode

DEEP_RESEARCH_MODE: Final[AgentMode] = "deep_research"
CODE_MODE: Final[AgentMode] = "code"

_RESEARCH_HINTS = (
    "research",
    "investigate",
    "analyze",
    "analysis",
    "compare",
    "sources",
    "evidence",
    "citations",
    "literature",
    "market scan",
)
_EXECUTION_HINTS = (
    "build",
    "implement",
    "fix",
    "debug",
    "run",
    "execute",
    "write code",
    "refactor",
    "test",
    "deploy",
    "shell",
    "command",
)
_FORCED_MODE_PATTERN = re.compile(
    r"\b(ignore|bypass|override|skip)\b.{0,40}\b(orchestrator|routing|policy|mode)\b",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """Structured node-level route decision."""

    selected_mode: AgentMode
    reason: str
    confidence: float
    bypass_attempt_detected: bool


class OrchestratorModeRouter:
    """Classify user intent and route to specialist modes."""

    @staticmethod
    def classify(instruction: str, *, requested_mode: str | None = None) -> RouteDecision:
        """Return deterministic specialist-mode routing for orchestrator node."""
        normalized_instruction = " ".join(str(instruction or "").strip().lower().split())
        bypass_attempt = bool(_FORCED_MODE_PATTERN.search(normalized_instruction))

        # Explicitly ignore user-supplied mode coercion attempts inside task text.
        # The orchestrator router chooses specialist mode from detected intent only.
        _ = requested_mode

        if any(hint in normalized_instruction for hint in _RESEARCH_HINTS):
            return RouteDecision(
                selected_mode=DEEP_RESEARCH_MODE,
                reason="intent_detected:research",
                confidence=0.82,
                bypass_attempt_detected=bypass_attempt,
            )
        if any(hint in normalized_instruction for hint in _EXECUTION_HINTS):
            return RouteDecision(
                selected_mode=CODE_MODE,
                reason="intent_detected:build_or_execution",
                confidence=0.86,
                bypass_attempt_detected=bypass_attempt,
            )

        return RouteDecision(
            selected_mode=CODE_MODE,
            reason="fallback:default_code_mode",
            confidence=0.55,
            bypass_attempt_detected=bypass_attempt,
        )


def build_synthesis(
    *,
    decision: RouteDecision,
    primary_result: dict[str, Any],
    fallback_result: dict[str, Any] | None,
) -> str:
    """Create final orchestrator synthesis using delegated child results."""
    child_refs = [f"child:primary:{decision.selected_mode}"]
    if fallback_result is not None:
        child_refs.append("child:fallback:code")
    summary = str(primary_result.get("summary", "")).strip()
    if not summary:
        summary = str(primary_result.get("error", "No summary provided by delegated mode.")).strip()
    return (
        f"Orchestrator routed to '{decision.selected_mode}' ({decision.reason}). "
        f"References: {', '.join(child_refs)}. Synthesis: {summary}"
    )
