"""Mode policy helpers for Aegis system-level subagents."""

from __future__ import annotations

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
