"""Mode policy helpers for immutable, system-owned agent modes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

AgentMode = str


@dataclass(frozen=True, slots=True)
class ModeDefinition:
    """Canonical system-owned mode metadata."""

    key: AgentMode
    label: str
    system_hint: str
    read_only: bool
    blocked_tools: frozenset[str]
    allow_subagents: bool
    immutable: bool = True
    owner: str = "system"

DEFAULT_AGENT_MODE: Final[AgentMode] = "orchestrator"

# Tools that execute side effects / mutations and are therefore code-mode only.
EXECUTION_BLOCKED_TOOLS: Final[set[str]] = {
    "go_to_url",
    "click",
    "type_text",
    "scroll",
    "go_back",
    "wait",
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
    "github_repo_diff",
    "github_commit_changes",
    "github_push_branch",
    "github_create_pull_request",
}

READ_ONLY_ALLOWED_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "screenshot",
        "web_search",
        "extract_page",
        "list_files",
        "read_file",
        "ask_user_input",
        "summarize_task",
        "confirm_plan",
        "memory_search",
        "memory_read",
        "github_list_repos",
        "github_get_issues",
        "github_get_pull_requests",
        "github_get_file",
        "done",
        "error",
    }
)

CANONICAL_MODE_ORDER: Final[tuple[AgentMode, ...]] = (
    "orchestrator",
    "planner",
    "architect",
    "deep_research",
    "code",
)
PROTECTED_MODE_POLICY_FIELDS: Final[frozenset[str]] = frozenset(
    {"key", "label", "system_hint", "read_only", "blocked_tools", "allow_subagents", "immutable", "owner"}
)
ADMIN_EDITABLE_MODE_METADATA_FIELDS: Final[frozenset[str]] = frozenset({"description", "emoji", "sort_order"})

MODE_REGISTRY: Final[dict[AgentMode, ModeDefinition]] = {
    "orchestrator": ModeDefinition(
        key="orchestrator",
        label="Orchestrator",
        system_hint=(
            "Route each request to the best specialist mode (planner, architect, deep_research, or code), "
            "synthesize outputs, and present a unified final answer without executing tools."
        ),
        read_only=True,
        blocked_tools=frozenset(EXECUTION_BLOCKED_TOOLS),
        allow_subagents=False,
    ),
    "planner": ModeDefinition(
        key="planner",
        label="Planner",
        system_hint="Produce clear, executable plans, milestones, and risk-aware sequencing without executing tools.",
        read_only=True,
        blocked_tools=frozenset(EXECUTION_BLOCKED_TOOLS),
        allow_subagents=False,
    ),
    "architect": ModeDefinition(
        key="architect",
        label="Architect",
        system_hint="Provide architecture decisions, tradeoffs, and implementation blueprints without tool execution.",
        read_only=True,
        blocked_tools=frozenset(EXECUTION_BLOCKED_TOOLS),
        allow_subagents=False,
    ),
    "deep_research": ModeDefinition(
        key="deep_research",
        label="Deep Research",
        system_hint="Deliver evidence-based analysis and synthesis from available knowledge without tool execution.",
        read_only=True,
        blocked_tools=frozenset(EXECUTION_BLOCKED_TOOLS),
        allow_subagents=False,
    ),
    "code": ModeDefinition(
        key="code",
        label="Code",
        system_hint="Perform implementation tasks using tools safely; this is the only mode allowed to spawn subagents.",
        read_only=False,
        blocked_tools=frozenset(),
        allow_subagents=True,
    ),
}

MODE_LABELS: Final[dict[AgentMode, str]] = {mode: MODE_REGISTRY[mode].label for mode in CANONICAL_MODE_ORDER}
MODE_SYSTEM_HINTS: Final[dict[AgentMode, str]] = {mode: MODE_REGISTRY[mode].system_hint for mode in CANONICAL_MODE_ORDER}
READ_ONLY_MODES: Final[set[AgentMode]] = {mode for mode, definition in MODE_REGISTRY.items() if definition.read_only}
MODE_CAPABILITY_MATRIX: Final[dict[AgentMode, dict[str, object]]] = {
    mode: {
        "read_only": definition.read_only,
        "allow_subagents": definition.allow_subagents,
        "blocked_tools": frozenset(definition.blocked_tools),
    }
    for mode, definition in MODE_REGISTRY.items()
}


def normalize_agent_mode(value: object) -> AgentMode:
    """Normalize unknown mode values to the default mode."""
    candidate = str(value or "").strip().lower()
    if candidate in MODE_LABELS:
        return candidate
    return DEFAULT_AGENT_MODE


def validate_requested_mode(value: object) -> tuple[AgentMode, bool]:
    """Return (effective_mode, is_valid_request)."""
    raw = str(value or "").strip().lower()
    if raw in MODE_REGISTRY:
        return raw, True
    return DEFAULT_AGENT_MODE, False


def blocked_tools_for_mode(mode: AgentMode) -> set[str]:
    """Return tools that must be blocked for the requested mode."""
    normalized_mode = normalize_agent_mode(mode)
    return set(MODE_CAPABILITY_MATRIX[normalized_mode]["blocked_tools"])


def is_tool_allowed_for_mode(mode: AgentMode, tool_name: str) -> bool:
    """Return whether a tool is allowed for the requested mode."""
    normalized_mode = normalize_agent_mode(mode)
    tool = str(tool_name or "").strip().lower()
    if not tool:
        return False
    return tool not in blocked_tools_for_mode(normalized_mode)


def allowed_tool_alternatives(mode: AgentMode, *, limit: int = 8) -> list[str]:
    """Return deterministic allowed tool suggestions for refusal payloads."""
    normalized_mode = normalize_agent_mode(mode)
    if normalized_mode in READ_ONLY_MODES:
        return list(sorted(READ_ONLY_ALLOWED_TOOLS))[: max(1, limit)]
    return []


def mode_definitions() -> list[ModeDefinition]:
    """Return immutable mode definitions in canonical order."""
    return [MODE_REGISTRY[mode] for mode in CANONICAL_MODE_ORDER]


def serialize_mode_definition(mode: AgentMode) -> dict[str, object]:
    """Return a JSON-friendly mode definition payload."""
    definition = MODE_REGISTRY[normalize_agent_mode(mode)]
    return {
        "key": definition.key,
        "label": definition.label,
        "system_hint": definition.system_hint,
        "read_only": definition.read_only,
        "blocked_tools": sorted(definition.blocked_tools),
        "allow_subagents": definition.allow_subagents,
        "immutable": definition.immutable,
        "owner": definition.owner,
    }
