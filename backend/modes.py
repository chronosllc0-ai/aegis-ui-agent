"""Mode policy and registry helpers for Aegis system-level subagents."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

AgentMode = str

DEFAULT_AGENT_MODE: Final[AgentMode] = "orchestrator"

MODE_LABELS: Final[dict[AgentMode, str]] = {
    "orchestrator": "Orchestrator",
    "planner": "Planner",
    "architect": "Architect",
    "deep_research": "Deep Research",
    "code": "Code",
}

MODE_SYSTEM_HINTS: Final[dict[AgentMode, str]] = {
    "orchestrator": (
        "Route each request to the best specialist mode (planner, architect, deep_research, or code), "
        "synthesize outputs, and present a unified final answer."
    ),
    "planner": "Produce clear, executable plans, milestones, and risk-aware sequencing without executing tools.",
    "architect": "Provide architecture decisions, tradeoffs, and implementation blueprints without tool execution.",
    "deep_research": "Deliver evidence-based analysis and synthesis from available knowledge without tool execution.",
    "code": "Perform implementation tasks using tools safely; this is the only mode allowed to spawn subagents.",
}

READ_ONLY_MODES: Final[set[AgentMode]] = {"planner", "architect", "deep_research"}

# Tools blocked for read-only modes.
READ_ONLY_BLOCKED_TOOLS: Final[set[str]] = {
    "go_to_url",
    "click",
    "type_text",
    "scroll",
    "go_back",
    "wait",
    "web_search",
    "extract_page",
    "write_file",
    "exec_python",
    "exec_javascript",
    "exec_shell",
    "memory_write",
    "memory_patch",
    "cron_write",
    "cron_patch",
    "cron_delete",
    "spawn_subagent",
    "message_subagent",
    "github_create_issue",
    "github_create_comment",
    "github_clone_repo",
    "github_create_branch",
    "github_repo_status",
    "github_diff",
    "github_commit",
    "github_push",
    "github_create_pr",
    "github_set_review",
}

ORCHESTRATOR_BLOCKED_TOOLS: Final[set[str]] = {"spawn_subagent"}
ADMIN_EDITABLE_MODE_METADATA_FIELDS: Final[set[str]] = {
    "title",
    "description",
    "badge",
    "sort_order",
}


@dataclass(frozen=True, slots=True)
class ModeDefinition:
    """Immutable metadata describing a built-in agent mode."""

    key: AgentMode
    label: str
    default_instruction: str
    read_only: bool
    blocked_tools: tuple[str, ...]


def normalize_agent_mode(value: object) -> AgentMode:
    """Normalize unknown mode values to the default mode."""
    candidate = str(value or "").strip().lower()
    if candidate in MODE_LABELS:
        return candidate
    return DEFAULT_AGENT_MODE


def blocked_tools_for_mode(mode: AgentMode) -> set[str]:
    """Return tools that must be blocked for the requested mode."""
    normalized_mode = normalize_agent_mode(mode)
    if normalized_mode in READ_ONLY_MODES:
        return set(READ_ONLY_BLOCKED_TOOLS)
    if normalized_mode == "orchestrator":
        return set(ORCHESTRATOR_BLOCKED_TOOLS)
    return set()


def mode_definitions() -> tuple[ModeDefinition, ...]:
    """Return built-in immutable mode definitions in UI display order."""
    ordered_modes: tuple[AgentMode, ...] = ("orchestrator", "planner", "architect", "deep_research", "code")
    definitions: list[ModeDefinition] = []
    for mode in ordered_modes:
        definitions.append(
            ModeDefinition(
                key=mode,
                label=MODE_LABELS[mode],
                default_instruction=MODE_SYSTEM_HINTS[mode],
                read_only=mode in READ_ONLY_MODES,
                blocked_tools=tuple(sorted(blocked_tools_for_mode(mode))),
            )
        )
    return tuple(definitions)


def serialize_mode_definition(mode: AgentMode) -> dict[str, object]:
    """Serialize one mode definition for API responses."""
    normalized_mode = normalize_agent_mode(mode)
    definition = next((item for item in mode_definitions() if item.key == normalized_mode), None)
    if not definition:
        definition = mode_definitions()[0]
    payload = asdict(definition)
    payload["blocked_tools_count"] = len(definition.blocked_tools)
    return payload
