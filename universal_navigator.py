"""Universal LLM navigator — provider-agnostic vision + tool-calling loop.

Replaces the Gemini ADK-only orchestrator for non-Gemini providers.
Works with any BaseProvider that supports vision (OpenAI, Anthropic, xAI,
OpenRouter, or Gemini via the providers adapter layer).
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy.exc import SQLAlchemyError

from config import settings as _app_settings
from backend.admin.platform_settings import GLOBAL_INSTRUCTION_KEY
from backend.github_repo_workspace import GitHubRepoWorkspaceManager
from backend.providers.base import BaseProvider, ChatMessage
from backend.skills.runtime_loader import RuntimeSkill, get_active_runtime_skills
from backend.session_workspace import (
    ensure_session_workspace,
    get_session_files_root,
    get_session_workspace_root,
    resolve_session_path,
)

logger = logging.getLogger(__name__)

MAX_STEPS = 40
RESULT_CHAR_LIMIT = 12_000
CODE_OUTPUT_LIMIT = 8_000
EXEC_ENV_BLOCKED_PREFIXES = (
    "API_",
    "AWS_",
    "AZURE_",
    "GCP_",
    "SECRET",
    "TOKEN",
    "PRIVATE",
    "CREDENTIAL",
)

ToolPermission = str
ToolRisk = str

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "screenshot",
        "description": "Capture the current browser viewport as a PNG.",
        "example": {"tool": "screenshot"},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "go_to_url",
        "description": "Navigate the browser to a URL.",
        "example": {"tool": "go_to_url", "url": "https://example.com"},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "click",
        "description": "Click browser coordinates from the screenshot.",
        "example": {"tool": "click", "x": 640, "y": 360, "description": "submit button"},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "type_text",
        "description": "Type text, optionally focusing an input at coordinates first.",
        "example": {"tool": "type_text", "text": "hello world", "x": 420, "y": 240},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "scroll",
        "description": "Scroll the browser viewport up or down.",
        "example": {"tool": "scroll", "direction": "down", "amount": 400},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "go_back",
        "description": "Go back one page in browser history.",
        "example": {"tool": "go_back"},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "wait",
        "description": "Pause briefly for loading or UI transitions.",
        "example": {"tool": "wait", "seconds": 1.5},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "web_search",
        "description": "Search the public web and return ranked results.",
        "example": {"tool": "web_search", "query": "GitHub Actions cache key strategy", "count": 5},
        "risk": "low",
        "default_permission": "auto",
        "subagent_available": True,
    },
    {
        "name": "extract_page",
        "description": "Fetch a URL and return its title plus cleaned text content.",
        "example": {"tool": "extract_page", "url": "https://example.com/docs"},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "list_files",
        "description": "List files or directories inside the current session workspace.",
        "example": {"tool": "list_files", "path": ".", "recursive": False, "max_depth": 2},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file from the current session workspace.",
        "example": {"tool": "read_file", "path": "notes/todo.txt", "start_line": 1, "max_lines": 200},
        "risk": "medium",
        "default_permission": "auto",
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a UTF-8 text file inside the session workspace.",
        "example": {"tool": "write_file", "path": "notes/plan.md", "content": "# Plan\n- item 1"},
        "risk": "high",
        "default_permission": "confirm",
    },
    {
        "name": "exec_python",
        "description": "Run Python code inside the current session workspace.",
        "example": {"tool": "exec_python", "code": "print('hello')", "cwd": ".", "timeout_seconds": 30},
        "risk": "high",
        "default_permission": "confirm",
    },
    {
        "name": "exec_javascript",
        "description": "Run Node.js JavaScript inside the current session workspace.",
        "example": {"tool": "exec_javascript", "code": "console.log('hello')", "cwd": ".", "timeout_seconds": 30},
        "risk": "high",
        "default_permission": "confirm",
    },
    {
        "name": "exec_shell",
        "description": "Run a shell command inside the current session workspace sandbox.",
        "example": {"tool": "exec_shell", "command": "pytest -q", "cwd": ".", "timeout_seconds": 60},
        "risk": "high",
        "default_permission": "confirm",
        "subagent_available": True,
    },
    {
        "name": "ask_user_input",
        "description": "Pause execution and ask the user a clarifying question.",
        "example": {"tool": "ask_user_input", "question": "Which repo should I modify?", "options": ["Repo A", "Repo B", "Let me tell you"]},
        "risk": "low",
        "default_permission": "auto",
        "subagent_available": True,
    },
    {
        "name": "summarize_task",
        "description": "Condense notes into a short summary when you want a reusable summary artifact.",
        "example": {"tool": "summarize_task", "content": "Long work log here", "max_sentences": 4},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "confirm_plan",
        "description": "Show a proposed plan to the user and wait for approval, revision, or cancellation.",
        "example": {"tool": "confirm_plan", "plan": ["Clone repo", "Run tests", "Patch failing code"]},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "memory_search",
        "description": "Semantic search through stored memories.",
        "example": {"tool": "memory_search", "query": "user's preferred reporting format"},
        "risk": "low",
        "default_permission": "auto",
        "subagent_available": True,
    },
    {
        "name": "memory_write",
        "description": "Store a new memory entry.",
        "example": {"tool": "memory_write", "content": "User prefers concise status updates.", "category": "preferences"},
        "risk": "medium",
        "default_permission": "auto",
    },
    {
        "name": "memory_read",
        "description": "Read a specific memory entry by ID.",
        "example": {"tool": "memory_read", "memory_id": "uuid"},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "memory_patch",
        "description": "Update a specific memory entry.",
        "example": {"tool": "memory_patch", "memory_id": "uuid", "content": "Updated fact"},
        "risk": "medium",
        "default_permission": "auto",
    },
    {
        "name": "cron_write",
        "description": "Create a scheduled automation.",
        "example": {"tool": "cron_write", "name": "Daily summary", "prompt": "Send the daily summary", "cron_expr": "0 9 * * *", "timezone": "UTC"},
        "risk": "medium",
        "default_permission": "confirm",
    },
    {
        "name": "cron_patch",
        "description": "Modify an existing scheduled automation.",
        "example": {"tool": "cron_patch", "task_id": "uuid", "cron_expr": "0 10 * * *"},
        "risk": "medium",
        "default_permission": "confirm",
    },
    {
        "name": "cron_delete",
        "description": "Delete a scheduled automation.",
        "example": {"tool": "cron_delete", "task_id": "uuid"},
        "risk": "high",
        "default_permission": "confirm",
    },
    {
        "name": "spawn_subagent",
        "description": "Spawn a focused sub-agent for parallel work.",
        "example": {"tool": "spawn_subagent", "instruction": "Research competitor pricing", "model": "same-as-current"},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "message_subagent",
        "description": "Send a steering update to a running sub-agent.",
        "example": {"tool": "message_subagent", "sub_id": "uuid", "message": "Focus on EU pricing only"},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "github_list_repos",
        "description": "List repositories available to the connected GitHub PAT.",
        "example": {"tool": "github_list_repos", "per_page": 20},
        "risk": "low",
        "default_permission": "auto",
        "requires_integration": "github-pat",
    },
    {
        "name": "github_get_issues",
        "description": "List issues in a GitHub repository.",
        "example": {"tool": "github_get_issues", "repo": "owner/repo", "state": "open"},
        "risk": "low",
        "default_permission": "auto",
        "requires_integration": "github-pat",
    },
    {
        "name": "github_create_issue",
        "description": "Create a GitHub issue.",
        "example": {"tool": "github_create_issue", "repo": "owner/repo", "title": "Bug report", "body": "Details"},
        "risk": "medium",
        "default_permission": "confirm",
        "requires_integration": "github-pat",
    },
    {
        "name": "github_get_pull_requests",
        "description": "List pull requests in a GitHub repository.",
        "example": {"tool": "github_get_pull_requests", "repo": "owner/repo", "state": "open"},
        "risk": "low",
        "default_permission": "auto",
        "requires_integration": "github-pat",
    },
    {
        "name": "github_create_comment",
        "description": "Create a GitHub issue or PR comment.",
        "example": {"tool": "github_create_comment", "repo": "owner/repo", "issue_number": 42, "body": "Looks good"},
        "risk": "medium",
        "default_permission": "confirm",
        "requires_integration": "github-pat",
    },
    {
        "name": "github_get_file",
        "description": "Read a file directly from a GitHub repository via the API.",
        "example": {"tool": "github_get_file", "repo": "owner/repo", "path": "README.md", "ref": "main"},
        "risk": "low",
        "default_permission": "auto",
        "requires_integration": "github-pat",
    },
    {
        "name": "github_clone_repo",
        "description": "Clone a GitHub repository into the local session workspace so you can inspect and edit it.",
        "example": {"tool": "github_clone_repo", "repo": "owner/repo", "ref": "main"},
        "risk": "low",
        "default_permission": "auto",
        "requires_integration": "github-pat",
    },
    {
        "name": "github_create_branch",
        "description": "Create or reset a local branch inside a cloned repository.",
        "example": {"tool": "github_create_branch", "local_path": "/tmp/.../repos/owner__repo", "branch_name": "feat/my-change", "base_ref": "main"},
        "risk": "low",
        "default_permission": "auto",
        "requires_integration": "github-pat",
    },
    {
        "name": "github_repo_status",
        "description": "Inspect local git status for a cloned repository.",
        "example": {"tool": "github_repo_status", "local_path": "/tmp/.../repos/owner__repo"},
        "risk": "low",
        "default_permission": "auto",
        "requires_integration": "github-pat",
    },
    {
        "name": "github_repo_diff",
        "description": "Read the local git diff for a cloned repository.",
        "example": {"tool": "github_repo_diff", "local_path": "/tmp/.../repos/owner__repo", "staged": False},
        "risk": "low",
        "default_permission": "auto",
        "requires_integration": "github-pat",
    },
    {
        "name": "github_commit_changes",
        "description": "Stage all local changes in a cloned repository and create a commit.",
        "example": {"tool": "github_commit_changes", "local_path": "/tmp/.../repos/owner__repo", "message": "feat: update workflow"},
        "risk": "medium",
        "default_permission": "confirm",
        "requires_integration": "github-pat",
    },
    {
        "name": "github_push_branch",
        "description": "Push the current branch of a cloned repository back to GitHub.",
        "example": {"tool": "github_push_branch", "local_path": "/tmp/.../repos/owner__repo", "branch": "feat/my-change"},
        "risk": "high",
        "default_permission": "confirm",
        "requires_integration": "github-pat",
    },
    {
        "name": "github_create_pull_request",
        "description": "Open a pull request from the cloned repository using GitHub CLI.",
        "example": {"tool": "github_create_pull_request", "local_path": "/tmp/.../repos/owner__repo", "title": "feat: improve flow", "body": "Summary", "base": "main"},
        "risk": "high",
        "default_permission": "confirm",
        "requires_integration": "github-pat",
    },
    {
        "name": "done",
        "description": "Finish the task and provide a concise summary.",
        "example": {"tool": "done", "summary": "Task completed."},
        "risk": "low",
        "default_permission": "auto",
    },
    {
        "name": "error",
        "description": "Stop the task with an unrecoverable error.",
        "example": {"tool": "error", "message": "Blocked by missing credentials."},
        "risk": "low",
        "default_permission": "auto",
    },
]
TOOL_INDEX = {tool["name"]: tool for tool in TOOL_DEFINITIONS}


def _truncate(text: str, limit: int = RESULT_CHAR_LIMIT) -> str:
    """Trim long tool results before sending them back to the model."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n\n[truncated {len(text) - limit} characters]"


def _json_result(payload: Any) -> str:
    """Serialize a result payload for the next model turn."""
    return _truncate(json.dumps(payload, ensure_ascii=False, indent=2))


def _strip_html(markup: str) -> str:
    """Convert rough HTML into plain text without external dependencies."""
    without_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", markup, flags=re.IGNORECASE | re.DOTALL)
    no_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def _canonical_integration_id(value: str) -> str:
    """Normalize integration ids so legacy github ids still resolve."""
    normalized = value.strip().lower()
    if normalized == "github":
        return "github-pat"
    return normalized


def _connected_integrations(settings: dict[str, Any]) -> set[str]:
    """Return connected integration ids from websocket session settings."""
    connected: set[str] = set()
    for raw in settings.get("integrations", []) or []:
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status", "connected")).strip().lower()
        enabled = bool(raw.get("enabled", True))
        if not enabled or status not in {"connected", "ok", "ready", "success", ""}:
            continue
        integration_id = _canonical_integration_id(str(raw.get("id", "")))
        if integration_id:
            connected.add(integration_id)
    return connected


def _available_tools(settings: dict[str, Any], *, is_subagent: bool) -> list[dict[str, Any]]:
    """Resolve the current tool manifest after permissions and integration gating."""
    disabled_tools = {str(item) for item in settings.get("disabled_tools", []) or []}
    connected_integrations = _connected_integrations(settings)
    subagent_allowlist: set[str] | None = None
    if is_subagent:
        from subagent_runtime import SUBAGENT_ALLOWED_TOOLS

        subagent_allowlist = set(SUBAGENT_ALLOWED_TOOLS)

    available: list[dict[str, Any]] = []
    for tool in TOOL_DEFINITIONS:
        name = str(tool["name"])
        if name in {"done", "error"}:
            available.append(tool)
            continue
        if name in disabled_tools:
            continue
        required_integration = tool.get("requires_integration")
        if required_integration and required_integration not in connected_integrations:
            continue
        if subagent_allowlist is not None and name not in subagent_allowlist:
            continue
        available.append(tool)
    return available


def _normalize_skill_content(content: str) -> str:
    """Trim and sanitize control characters in runtime skill content."""
    normalized = "".join(char for char in content if char in {"\n", "\t"} or (ord(char) >= 32 and ord(char) != 127))
    return normalized.strip()


def _estimate_tokens(text: str) -> int:
    """Estimate prompt tokens with a lightweight character heuristic."""
    return max(1, len(text) // 4)


def _assemble_runtime_skills_section(
    runtime_skills: list[RuntimeSkill],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Build runtime skill prompt section using priority-based token budgeting."""
    budget = max(int(_app_settings.SKILLS_MAX_TOKENS), 0)
    min_priority = _app_settings.SKILLS_MIN_PRIORITY
    baseline = datetime.min.replace(tzinfo=timezone.utc)
    sorted_skills = sorted(
        runtime_skills,
        key=lambda item: (
            item.priority,
            item.created_at or baseline,
            item.version_id,
        ),
        reverse=True,
    )

    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    chunks: list[str] = []
    used_tokens = 0
    budget_exceeded = False
    for skill in sorted_skills:
        if min_priority is not None and skill.priority < min_priority:
            excluded.append({"skill_id": skill.skill_id, "reason": "below_min_priority"})
            continue

        content = _normalize_skill_content(skill.content)
        if not content:
            excluded.append({"skill_id": skill.skill_id, "reason": "empty_or_malformed"})
            continue

        header = (
            f"[skill:{skill.skill_id}@{skill.version_id} source={skill.source} priority={skill.priority}]"
        )
        chunk = f"{header}\n{content}\n"
        estimated_tokens = _estimate_tokens(chunk)
        if used_tokens + estimated_tokens > budget:
            excluded.append({"skill_id": skill.skill_id, "reason": "budget_exceeded"})
            budget_exceeded = True
            continue
        used_tokens += estimated_tokens
        chunks.append(chunk)
        included.append(
            {
                "skill_id": skill.skill_id,
                "version": skill.version_id,
                "source": skill.source,
                "priority": skill.priority,
            }
        )

    if not chunks:
        return "", included, excluded

    body = "\n".join(chunks).strip()
    if budget_exceeded:
        body = f"{body}\n... [truncated due to skills token budget]"
    return f"\n\n### Active Skills (read-only directives)\n{body}\n", included, excluded


async def _load_runtime_skills(
    *,
    session_id: str,
    user_uid: str | None,
    settings: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Load and prepare runtime skills section. Fail-open unless configured otherwise."""
    if not user_uid:
        return "", [], []

    correlation_id = str(settings.get("correlation_id") or settings.get("request_id") or session_id)
    try:
        from backend.database import _session_factory

        if _session_factory is None:
            return "", [], []

        async with _session_factory() as db:
            runtime_skills = await get_active_runtime_skills(db, user_uid, session_id)
    except SQLAlchemyError as exc:
        logger.warning("Runtime skills unavailable (correlation_id=%s): %s", correlation_id, exc)
        if _app_settings.SKILLS_FAIL_CLOSED:
            raise
        return "", [], []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Runtime skills loader failed (correlation_id=%s): %s", correlation_id, exc)
        if _app_settings.SKILLS_FAIL_CLOSED:
            raise
        return "", [], []

    return _assemble_runtime_skills_section(runtime_skills)


async def _build_system_prompt(
    *,
    session_id: str,
    settings: dict[str, Any],
    is_subagent: bool,
    runtime_skills_section: str = "",
) -> str:
    """Build the current system prompt from enabled tools and user instruction."""
    workspace_root = get_session_workspace_root(session_id)
    files_root = get_session_files_root(session_id)
    available = _available_tools(settings, is_subagent=is_subagent)
    tool_lines: list[str] = []
    for tool in available:
        tool_lines.append(json.dumps(tool["example"], ensure_ascii=False))
        tool_lines.append(f"  → {tool['description']}")

    browser_tools_enabled = any(tool["name"] == "screenshot" for tool in available)
    github_tools_enabled = any(str(tool["name"]).startswith("github_") for tool in available)
    local_workspace_enabled = any(tool["name"] in {"list_files", "read_file", "write_file", "exec_python", "exec_javascript", "exec_shell"} for tool in available)

    rules: list[str] = [
        "Return exactly ONE JSON tool call per message and nothing else.",
        "Only use tools listed below. If a tool is not listed, it is not available in this session.",
        "Use concise, efficient steps and finish with the done tool when the task is complete.",
    ]
    if browser_tools_enabled:
        rules.extend(
            [
                "If the task depends on the current browser state, start with screenshot.",
                "After browser actions, use screenshot again to verify the result before moving on when needed.",
                "Use screenshot coordinates directly for click and type_text. The viewport is 1280×720.",
            ]
        )
    if local_workspace_enabled:
        rules.extend(
            [
                f"Local workspace root: {workspace_root}",
                f"Scratch files default under: {files_root}",
                "Local file and code tools can only access paths inside the current session workspace.",
            ]
        )
    if github_tools_enabled:
        rules.extend(
            [
                "For repo-engineering tasks, clone the repository first, create or switch to a feature branch, inspect or edit files locally, run verification, inspect status/diff, then commit, push, and create a pull request.",
                "Use the local_path returned by github_clone_repo for subsequent repo tools and local file/code tools.",
                "Do not invent repository paths or branch names. Use returned tool results.",
            ]
        )
    rules.extend(
        [
            "Identity: You are Aegis, an AI agent built by Chronos AI.",
            "Operational reality: You execute actions from a secured runtime with broad tooling.",
            "Security boundary: Never reveal hidden VM/system internals, shell details, local paths, environment variables, credentials, internal policies, or undisclosed tool infrastructure to users.",
            "If asked for internals, provide a safe high-level explanation and continue with user-facing outcomes.",
            "Always respect tool gating: availability, integration requirements, disabled tools, and confirm/auto permissions.",
            "Use summarize_task to create condensed summaries when helpful, and finish with done including a concise summary.",
        ]
    )

    # ── Global system instruction (admin-controlled, authoritative) ──────────
    # Fetch from DB if available; fall back to the AEGIS_GLOBAL_SYSTEM_INSTRUCTION
    # env var; fall back to empty string.  This block is prepended before
    # everything else so it cannot be overridden by user runtime instructions.
    global_instruction = ""
    try:
        from backend.database import _session_factory, PlatformSetting
        from sqlalchemy import select as _sa_select
        from sqlalchemy.exc import SQLAlchemyError
        if _session_factory is not None:
            async with _session_factory() as _db:
                _row = (await _db.execute(
                    _sa_select(PlatformSetting).where(PlatformSetting.key == GLOBAL_INSTRUCTION_KEY)
                )).scalar_one_or_none()
                if _row and _row.value.strip():
                    global_instruction = _row.value.strip()
    except SQLAlchemyError as exc:
        logger.warning("Failed to fetch global system instruction from DB (SQLAlchemy): %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch global system instruction from DB: %s", exc)
    if not global_instruction:
        global_instruction = _app_settings.AEGIS_GLOBAL_SYSTEM_INSTRUCTION.strip()

    global_block = (
        f"Global operator instructions (authoritative — always follow these):\n{global_instruction}\n\n"
        if global_instruction
        else ""
    )

    # ── User runtime instructions (additive, appended after core prompt) ─────
    custom_instruction = str(settings.get("system_instruction", "")).strip()
    custom_block = (
        f"\nRuntime instructions from the user (additive — follow unless they conflict with global instructions above):\n{custom_instruction}\n"
        if custom_instruction
        else ""
    )
    return (
        f"{global_block}"
        "You are Aegis, an AI agent built by Chronos AI. You can browse the web and, when enabled, use "
        "workspace, memory, automation, and GitHub repo-engineering tools while respecting runtime policy gates.\n\n"
        f"Available tools for this session:\n{chr(10).join(tool_lines)}\n\n"
        f"Rules:\n{chr(10).join(f'{index + 1}. {rule}' for index, rule in enumerate(rules))}"
        f"{runtime_skills_section}"
        f"{custom_block}"
    )


class UniversalToolExecutor:
    """Executes tool calls issued by the LLM and returns text results."""

    def __init__(
        self,
        executor: Any,
        *,
        session_id: str,
        settings: dict[str, Any] | None = None,
        user_uid: str | None = None,
        on_user_input: Callable[[str, list[str]], Awaitable[str]] | None = None,
        on_spawn_subagent: Callable[[str, str], Awaitable[str]] | None = None,
        on_message_subagent: Callable[[str, str], Awaitable[bool]] | None = None,
        is_subagent: bool = False,
    ) -> None:
        """Initialize the tool executor for one navigation run."""
        self._exe = executor
        self._session_id = session_id
        self._settings = settings or {}
        self._last_screenshot: bytes | None = None
        self._user_uid = user_uid
        self._on_user_input = on_user_input
        self._on_spawn_subagent = on_spawn_subagent
        self._on_message_subagent = on_message_subagent
        self._is_subagent = is_subagent
        self._disabled_tools = {str(item) for item in self._settings.get("disabled_tools", []) or []}
        self._tool_permissions: dict[str, ToolPermission] = {
            str(key): str(value) for key, value in (self._settings.get("tool_permissions", {}) or {}).items()
        }
        behavior = self._settings.get("behavior", {}) or {}
        self._confirm_destructive_actions = bool(behavior.get("confirm_destructive_actions", False))
        self._connected_integrations = _connected_integrations(self._settings)
        ensure_session_workspace(self._session_id)
        self._github_manager: GitHubRepoWorkspaceManager | None = None

    async def run(self, tool_call: dict[str, Any]) -> tuple[str, bytes | None]:
        """Execute a tool and return (text_result, optional_screenshot_bytes)."""
        tool = str(tool_call.get("tool", "")).strip()
        screenshot: bytes | None = None

        if tool in {"done", "error"}:
            return "", None

        unavailable_reason = self._tool_unavailable_reason(tool)
        if unavailable_reason:
            return unavailable_reason, None

        blocked_by_approval = await self._confirm_if_needed(tool_call)
        if blocked_by_approval:
            return blocked_by_approval, None

        try:
            if tool == "screenshot":
                screenshot = await self._exe.screenshot()
                self._last_screenshot = screenshot
                return "Screenshot captured.", screenshot

            if tool == "go_to_url":
                url = str(tool_call.get("url", "")).strip()
                if not url:
                    return "Error: url is required.", None
                result = await self._exe.goto(url)
                return f"Navigated to {result['url']} — title: {result.get('title', '')}", None

            if tool == "click":
                x = int(tool_call.get("x", 0))
                y = int(tool_call.get("y", 0))
                description = str(tool_call.get("description", "")).strip()
                result = await self._exe.click(x, y)
                suffix = f" ({description})" if description else ""
                return f"Clicked ({x}, {y}){suffix} — now at {result.get('url', '')}", None

            if tool == "type_text":
                text = str(tool_call.get("text", ""))
                x = tool_call.get("x")
                y = tool_call.get("y")
                await self._exe.type_text(text, int(x) if x is not None else None, int(y) if y is not None else None)
                return f"Typed {len(text)} characters.", None

            if tool == "scroll":
                direction = str(tool_call.get("direction", "down"))
                amount = int(tool_call.get("amount", 300))
                await self._exe.scroll(direction, amount)
                return f"Scrolled {direction} {amount}px.", None

            if tool == "go_back":
                result = await self._exe.go_back()
                return f"Went back to {result.get('url', '')}", None

            if tool == "wait":
                seconds = min(max(float(tool_call.get("seconds", 1.5)), 0.0), 10.0)
                await asyncio.sleep(seconds)
                return f"Waited {seconds:.1f}s.", None

            if tool == "web_search":
                query = str(tool_call.get("query", "")).strip()
                count = min(max(int(tool_call.get("count", 5)), 1), 10)
                if not query:
                    return "web_search error: query is required.", None
                results = await self._web_search(query, count)
                return _json_result({"ok": True, "query": query, "results": results}), None

            if tool == "extract_page":
                url = str(tool_call.get("url", "")).strip()
                if not url:
                    return "extract_page error: url is required.", None
                page = await self._extract_page(url)
                return _json_result(page), None

            if tool == "list_files":
                path = str(tool_call.get("path", "."))
                recursive = bool(tool_call.get("recursive", False))
                max_depth = min(max(int(tool_call.get("max_depth", 2)), 0), 6)
                listing = self._list_files(path, recursive=recursive, max_depth=max_depth)
                return _json_result(listing), None

            if tool == "read_file":
                path = str(tool_call.get("path", "")).strip()
                if not path:
                    return "read_file error: path is required.", None
                start_line = max(int(tool_call.get("start_line", 1)), 1)
                max_lines = min(max(int(tool_call.get("max_lines", 200)), 1), 800)
                return _json_result(self._read_file(path, start_line=start_line, max_lines=max_lines)), None

            if tool == "write_file":
                path = str(tool_call.get("path", "")).strip()
                content = str(tool_call.get("content", ""))
                if not path:
                    return "write_file error: path is required.", None
                result = self._write_file(path, content)
                return _json_result(result), None

            if tool == "exec_python":
                result = await self._run_code(tool_call, interpreter="python", suffix=".py")
                return _json_result(result), None

            if tool == "exec_javascript":
                result = await self._run_code(tool_call, interpreter="node", suffix=".mjs")
                return _json_result(result), None

            if tool == "exec_shell":
                result = await self._run_shell(tool_call)
                return _json_result(result), None

            if tool == "ask_user_input":
                question = str(tool_call.get("question", "")).strip()
                options = [str(item) for item in list(tool_call.get("options", []))][:4]
                if self._on_user_input:
                    answer = await self._on_user_input(question, options)
                    return f"User answered: {answer}", None
                return "No user input handler available.", None

            if tool == "summarize_task":
                content = str(tool_call.get("content") or tool_call.get("notes") or "").strip()
                max_sentences = min(max(int(tool_call.get("max_sentences", 4)), 1), 10)
                summary = self._summarize_text(content, max_sentences=max_sentences)
                return _json_result({"ok": True, "summary": summary}), None

            if tool == "confirm_plan":
                if not self._on_user_input:
                    return "confirm_plan error: no user approval handler is available.", None
                raw_plan = tool_call.get("plan") or tool_call.get("summary") or tool_call.get("content")
                if isinstance(raw_plan, list):
                    plan_lines = [f"- {str(item)}" for item in raw_plan]
                    plan_text = "\n".join(plan_lines)
                else:
                    plan_text = str(raw_plan or "").strip()
                answer = await self._on_user_input(
                    f"Approve this plan?\n{plan_text}",
                    ["Approve", "Revise", "Cancel"],
                )
                return _json_result({"ok": True, "response": answer}), None

            if tool == "memory_search":
                return await self._memory_search(tool_call), None

            if tool == "memory_write":
                return await self._memory_write(tool_call), None

            if tool == "memory_read":
                return await self._memory_read(tool_call), None

            if tool == "memory_patch":
                return await self._memory_patch(tool_call), None

            if tool == "cron_write":
                return await self._cron_write(tool_call), None

            if tool == "cron_patch":
                return await self._cron_patch(tool_call), None

            if tool == "cron_delete":
                return await self._cron_delete(tool_call), None

            if tool == "spawn_subagent":
                sub_instruction = str(tool_call.get("instruction", "")).strip()
                sub_model = str(tool_call.get("model", "")).strip()
                if not sub_instruction:
                    return "spawn_subagent error: instruction is required.", None
                if self._on_spawn_subagent:
                    sub_id = await self._on_spawn_subagent(sub_instruction, sub_model)
                    return f"Sub-agent spawned with id={sub_id}. It is now running independently.", None
                return "spawn_subagent is not available in this context.", None

            if tool == "message_subagent":
                sub_id = str(tool_call.get("sub_id", "")).strip()
                message = str(tool_call.get("message", "")).strip()
                if not sub_id or not message:
                    return "message_subagent error: sub_id and message are required.", None
                if self._on_message_subagent:
                    ok = await self._on_message_subagent(sub_id, message)
                    return f"Steering message {'sent' if ok else 'failed'} for sub-agent {sub_id}.", None
                return "message_subagent is not available in this context.", None

            if tool == "github_list_repos":
                github = await self._github()
                return _json_result(await github.list_repos(per_page=min(max(int(tool_call.get("per_page", 30)), 1), 100))), None

            if tool == "github_get_issues":
                github = await self._github()
                return _json_result(await github.get_issues(str(tool_call.get("repo", "")).strip(), state=str(tool_call.get("state", "open")))), None

            if tool == "github_create_issue":
                github = await self._github()
                return _json_result(await github.create_issue(str(tool_call.get("repo", "")).strip(), str(tool_call.get("title", "")).strip(), str(tool_call.get("body", "")))), None

            if tool == "github_get_pull_requests":
                github = await self._github()
                return _json_result(await github.get_pull_requests(str(tool_call.get("repo", "")).strip(), state=str(tool_call.get("state", "open")))), None

            if tool == "github_create_comment":
                github = await self._github()
                return _json_result(await github.create_comment(str(tool_call.get("repo", "")).strip(), int(tool_call.get("issue_number", 0)), str(tool_call.get("body", "")))), None

            if tool == "github_get_file":
                github = await self._github()
                return _json_result(await github.get_file(str(tool_call.get("repo", "")).strip(), str(tool_call.get("path", "")).strip(), ref=str(tool_call.get("ref", "")).strip() or None)), None

            if tool == "github_clone_repo":
                github = await self._github()
                return _json_result(await github.clone_repo(str(tool_call.get("repo", "")).strip(), ref=str(tool_call.get("ref", "")).strip() or None)), None

            if tool == "github_create_branch":
                github = await self._github()
                return _json_result(await github.create_branch(str(tool_call.get("local_path", "")).strip(), str(tool_call.get("branch_name", "")).strip(), base_ref=str(tool_call.get("base_ref", "")).strip() or None)), None

            if tool == "github_repo_status":
                github = await self._github()
                return _json_result(await github.repo_status(str(tool_call.get("local_path", "")).strip())), None

            if tool == "github_repo_diff":
                github = await self._github()
                return _json_result(await github.repo_diff(str(tool_call.get("local_path", "")).strip(), staged=bool(tool_call.get("staged", False)), pathspec=str(tool_call.get("pathspec", "")).strip() or None)), None

            if tool == "github_commit_changes":
                github = await self._github()
                return _json_result(await github.commit_changes(str(tool_call.get("local_path", "")).strip(), str(tool_call.get("message", "")).strip())), None

            if tool == "github_push_branch":
                github = await self._github()
                return _json_result(await github.push_branch(str(tool_call.get("local_path", "")).strip(), branch=str(tool_call.get("branch", "")).strip() or None)), None

            if tool == "github_create_pull_request":
                github = await self._github()
                return _json_result(await github.create_pull_request(
                    str(tool_call.get("local_path", "")).strip(),
                    str(tool_call.get("title", "")).strip(),
                    str(tool_call.get("body", "")),
                    base=str(tool_call.get("base", "main")).strip() or "main",
                    head=str(tool_call.get("head", "")).strip() or None,
                    draft=bool(tool_call.get("draft", False)),
                )), None

            return f"Unknown tool: {tool}", None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tool %s failed: %s", tool, exc)
            return f"Tool error ({tool}): {exc}", None

    def _tool_unavailable_reason(self, tool: str) -> str | None:
        """Explain why a tool is not available in the current session."""
        if not tool:
            return "Tool name is required."
        metadata = TOOL_INDEX.get(tool)
        if metadata is None:
            return None
        if self._is_subagent:
            from subagent_runtime import SUBAGENT_ALLOWED_TOOLS

            if tool not in SUBAGENT_ALLOWED_TOOLS:
                return f"Tool '{tool}' is not available to sub-agents."
        if tool in self._disabled_tools:
            return f"Tool '{tool}' is currently disabled in Settings → Tools."
        required_integration = metadata.get("requires_integration")
        if required_integration and required_integration not in self._connected_integrations:
            return f"Tool '{tool}' requires a connected GitHub PAT in Settings → Connections."
        return None

    async def _confirm_if_needed(self, tool_call: dict[str, Any]) -> str | None:
        """Pause for approval when the current tool requires it."""
        tool = str(tool_call.get("tool", "")).strip()
        if not tool:
            return None
        if not self._tool_requires_confirmation(tool):
            return None
        if not self._on_user_input:
            return f"Tool '{tool}' requires approval, but no approval channel is available."
        answer = await self._on_user_input(
            f"Allow Aegis to run {tool}?\n{self._tool_args_summary(tool_call)}",
            ["Approve", "Reject", "Let me tell you"],
        )
        normalized = answer.strip().lower()
        if normalized.startswith("approve") or normalized in {"yes", "allow", "ok", "okay"}:
            return None
        return f"User declined tool '{tool}' with response: {answer}"

    def _tool_requires_confirmation(self, tool: str) -> bool:
        """Return whether the current tool should stop for approval."""
        explicit = self._tool_permissions.get(tool)
        if explicit == "confirm":
            return True
        if explicit == "auto":
            return False
        metadata = TOOL_INDEX.get(tool, {})
        default_permission = str(metadata.get("default_permission", "auto"))
        if default_permission == "confirm":
            return True
        risk = str(metadata.get("risk", "low"))
        return self._confirm_destructive_actions and risk == "high"

    def _tool_args_summary(self, tool_call: dict[str, Any]) -> str:
        """Return a compact approval summary for a pending tool call."""
        summary_parts: list[str] = []
        for key, value in tool_call.items():
            if key == "tool":
                continue
            rendered = value
            if isinstance(value, str) and len(value) > 240:
                rendered = f"{value[:240]}…"
            summary_parts.append(f"{key}={rendered}")
        return "; ".join(summary_parts) if summary_parts else "No arguments provided."

    async def _github(self) -> GitHubRepoWorkspaceManager:
        """Return the GitHub repo workspace manager for this session."""
        if self._github_manager is not None:
            return self._github_manager
        token = ""
        for raw in self._settings.get("integrations", []) or []:
            if not isinstance(raw, dict):
                continue
            integration_id = _canonical_integration_id(str(raw.get("id", "")))
            if integration_id != "github-pat":
                continue
            config = raw.get("settings", {}) or {}
            token = str(config.get("token", "")).strip()
            if token:
                break
        if not token:
            raise RuntimeError("No connected GitHub PAT token is available in this session.")
        self._github_manager = GitHubRepoWorkspaceManager(session_id=self._session_id, token=token)
        await self._github_manager.ensure_identity()
        return self._github_manager

    async def _web_search(self, query: str, count: int) -> list[dict[str, str]]:
        """Search using Brave Search API when key is set, else fall back to DuckDuckGo HTML.

        If Brave Search is configured but the request fails (network error, bad key,
        rate-limit, etc.) the error is logged and the method falls through to the
        DuckDuckGo HTML scraper so the user always gets some results.
        """
        if _app_settings.BRAVE_SEARCH_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(
                        "https://api.search.brave.com/res/v1/web/search",
                        params={"q": query, "count": count},
                        headers={"Accept": "application/json", "X-Subscription-Token": _app_settings.BRAVE_SEARCH_API_KEY},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                results = []
                for item in data.get("web", {}).get("results", []):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("description", ""),
                    })
                return results
            except httpx.HTTPStatusError as exc:
                logger.warning("Brave Search HTTP error %s for query %r — falling back to DuckDuckGo", exc.response.status_code, query)
            except httpx.RequestError as exc:
                logger.warning("Brave Search request error for query %r: %s — falling back to DuckDuckGo", query, exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Brave Search unexpected error for query %r: %s — falling back to DuckDuckGo", query, exc)
        # Fallback: DuckDuckGo HTML scraping
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 Aegis"}) as client:
            response = await client.get("https://html.duckduckgo.com/html/", params={"q": query})
            response.raise_for_status()
        html_text = response.text
        results: list[dict[str, str]] = []
        for match in re.finditer(r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>', html_text, flags=re.IGNORECASE | re.DOTALL):
            url = html.unescape(match.group("url"))
            title = _strip_html(match.group("title"))
            rest = html_text[match.end(): match.end() + 1600]
            snippet_match = re.search(r'class="result__snippet"[^>]*>(?P<snippet>.*?)</(?:a|div)>', rest, flags=re.IGNORECASE | re.DOTALL)
            snippet = _strip_html(snippet_match.group("snippet")) if snippet_match else ""
            results.append({"title": title, "url": url, "snippet": snippet})
            if len(results) >= count:
                break
        return results

    async def _extract_page(self, url: str) -> dict[str, Any]:
        """Fetch a page and return a title plus cleaned body text."""
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 Aegis"}) as client:
            response = await client.get(url)
            response.raise_for_status()
        title_match = re.search(r"<title[^>]*>(.*?)</title>", response.text, flags=re.IGNORECASE | re.DOTALL)
        title = _strip_html(title_match.group(1)) if title_match else ""
        content = _truncate(_strip_html(response.text), limit=5000)
        return {"ok": True, "url": str(response.url), "title": title, "content": content}

    def _list_files(self, path: str, *, recursive: bool, max_depth: int) -> dict[str, Any]:
        """List directory contents in the session workspace."""
        root = resolve_session_path(self._session_id, path)
        if not root.exists():
            raise RuntimeError("Requested path does not exist.")
        if root.is_file():
            return {
                "ok": True,
                "path": str(root),
                "entries": [self._format_path_entry(root, base=root.parent)],
            }

        entries: list[dict[str, Any]] = []
        base_depth = len(root.parts)
        iterator = root.rglob("*") if recursive else root.iterdir()
        for item in iterator:
            current_depth = len(item.parts) - base_depth
            if current_depth > max_depth:
                continue
            entries.append(self._format_path_entry(item, base=root))
            if len(entries) >= 200:
                break
        entries.sort(key=lambda item: (item["type"] != "dir", item["path"]))
        return {"ok": True, "path": str(root), "entries": entries}

    def _format_path_entry(self, path: Path, *, base: Path) -> dict[str, Any]:
        """Format one file-system entry for a list_files response."""
        stat = path.stat()
        relative = path.relative_to(base)
        return {
            "path": str(relative) if str(relative) != "." else path.name,
            "type": "dir" if path.is_dir() else "file",
            "size": stat.st_size,
        }

    def _read_file(self, path: str, *, start_line: int, max_lines: int) -> dict[str, Any]:
        """Read a local UTF-8 text file inside the session workspace."""
        file_path = resolve_session_path(self._session_id, path)
        if not file_path.exists() or not file_path.is_file():
            raise RuntimeError("Requested file does not exist.")
        text = file_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        start_index = max(start_line - 1, 0)
        end_index = min(start_index + max_lines, len(lines))
        excerpt = "\n".join(lines[start_index:end_index])
        return {
            "ok": True,
            "path": str(file_path),
            "start_line": start_line,
            "end_line": end_index,
            "total_lines": len(lines),
            "content": _truncate(excerpt),
        }

    def _write_file(self, path: str, content: str) -> dict[str, Any]:
        """Write a local UTF-8 text file inside the session workspace."""
        file_path = resolve_session_path(self._session_id, path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(file_path), "bytes_written": len(content.encode('utf-8'))}

    async def _run_code(self, tool_call: dict[str, Any], *, interpreter: str, suffix: str) -> dict[str, Any]:
        """Execute Python or JavaScript code in the session workspace."""
        code = str(tool_call.get("code", ""))
        if not code.strip():
            raise RuntimeError("code is required")
        cwd = str(tool_call.get("cwd", ".")).strip() or "."
        cwd_path = resolve_session_path(self._session_id, cwd)
        workdir = cwd_path if cwd_path.is_dir() else cwd_path.parent
        workdir.mkdir(parents=True, exist_ok=True)
        filename = str(tool_call.get("filename", f"aegis_exec_{uuid4().hex}{suffix}"))
        script_path = resolve_session_path(self._session_id, str(Path(cwd) / filename) if not Path(filename).is_absolute() else filename)
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(code, encoding="utf-8")
        timeout = min(max(int(tool_call.get("timeout_seconds", 30)), 1), 120)
        env = {
            key: value
            for key, value in os.environ.items()
            if not any(key.upper().startswith(prefix) for prefix in EXEC_ENV_BLOCKED_PREFIXES)
        }
        env.setdefault("HOME", str(get_session_workspace_root(self._session_id)))
        process = await asyncio.create_subprocess_exec(
            interpreter,
            str(script_path),
            cwd=str(workdir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise RuntimeError(f"{interpreter} execution timed out after {timeout} seconds") from exc
        return {
            "ok": process.returncode == 0,
            "cwd": str(workdir),
            "script_path": str(script_path),
            "return_code": process.returncode,
            "stdout": _truncate(stdout.decode("utf-8", errors="replace"), CODE_OUTPUT_LIMIT),
            "stderr": _truncate(stderr.decode("utf-8", errors="replace"), CODE_OUTPUT_LIMIT),
        }

    async def _run_shell(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Execute a shell command in the session workspace."""
        command = str(tool_call.get("command", "")).strip()
        if not command:
            raise RuntimeError("command is required")
        cwd = str(tool_call.get("cwd", ".")).strip() or "."
        cwd_path = resolve_session_path(self._session_id, cwd)
        workdir = cwd_path if cwd_path.is_dir() else cwd_path.parent
        workdir.mkdir(parents=True, exist_ok=True)
        timeout = min(max(int(tool_call.get("timeout_seconds", 60)), 1), 180)
        env = {
            key: value
            for key, value in os.environ.items()
            if not any(key.upper().startswith(prefix) for prefix in EXEC_ENV_BLOCKED_PREFIXES)
        }
        env.setdefault("HOME", str(get_session_workspace_root(self._session_id)))
        env.setdefault("CI", "1")
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            command,
            cwd=str(workdir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise RuntimeError(f"shell command timed out after {timeout} seconds") from exc
        return {
            "ok": process.returncode == 0,
            "cwd": str(workdir),
            "command": command,
            "return_code": process.returncode,
            "stdout": _truncate(stdout.decode("utf-8", errors="replace"), CODE_OUTPUT_LIMIT),
            "stderr": _truncate(stderr.decode("utf-8", errors="replace"), CODE_OUTPUT_LIMIT),
        }

    def _summarize_text(self, content: str, *, max_sentences: int) -> str:
        """Create a small summary without calling the model again."""
        if not content:
            return ""
        sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", content) if segment.strip()]
        if not sentences:
            return _truncate(content, 600)
        return " ".join(sentences[:max_sentences])

    async def _memory_search(self, tool_call: dict[str, Any]) -> str:
        """Execute memory_search and return a serialized result."""
        query = str(tool_call.get("query", "")).strip()
        if not self._user_uid:
            return "Memory tools require an authenticated user."
        try:
            from backend.database import _session_factory
            from backend.memory.service import MemoryService

            if _session_factory is None:
                return "Database not ready."
            async with _session_factory() as session:
                results = await MemoryService.recall(session, self._user_uid, query, limit=5)
            return _json_result({"ok": True, "results": results})
        except Exception as exc:  # noqa: BLE001
            return f"memory_search error: {exc}"

    async def _memory_write(self, tool_call: dict[str, Any]) -> str:
        """Execute memory_write and return a serialized result."""
        content = str(tool_call.get("content", ""))
        category = str(tool_call.get("category", "general"))
        if not self._user_uid:
            return "Memory tools require an authenticated user."
        try:
            from backend.database import _session_factory
            from backend.memory.service import MemoryService

            if _session_factory is None:
                return "Database not ready."
            async with _session_factory() as session:
                entry = await MemoryService.store(session, self._user_uid, content, category=category)
            return _json_result({"ok": True, "entry": entry})
        except Exception as exc:  # noqa: BLE001
            return f"memory_write error: {exc}"

    async def _memory_read(self, tool_call: dict[str, Any]) -> str:
        """Execute memory_read and return a serialized result."""
        memory_id = str(tool_call.get("memory_id", ""))
        if not self._user_uid:
            return "Memory tools require an authenticated user."
        try:
            from backend.database import _session_factory
            from backend.memory.service import MemoryService

            if _session_factory is None:
                return "Database not ready."
            async with _session_factory() as session:
                entry = await MemoryService.get_memory(session, memory_id, self._user_uid)
            if not entry:
                return f"Memory {memory_id} not found."
            return _json_result({"ok": True, "entry": entry})
        except Exception as exc:  # noqa: BLE001
            return f"memory_read error: {exc}"

    async def _memory_patch(self, tool_call: dict[str, Any]) -> str:
        """Execute memory_patch and return a serialized result."""
        memory_id = str(tool_call.get("memory_id", ""))
        content = tool_call.get("content")
        category = tool_call.get("category")
        if not self._user_uid:
            return "Memory tools require an authenticated user."
        try:
            from backend.database import _session_factory
            from backend.memory.service import MemoryService

            if _session_factory is None:
                return "Database not ready."
            async with _session_factory() as session:
                updated = await MemoryService.update_memory(
                    session,
                    memory_id,
                    self._user_uid,
                    content=content,
                    category=category,
                )
            if not updated:
                return f"Memory {memory_id} not found or not updated."
            return _json_result({"ok": True, "memory_id": memory_id})
        except Exception as exc:  # noqa: BLE001
            return f"memory_patch error: {exc}"

    async def _cron_write(self, tool_call: dict[str, Any]) -> str:
        """Execute cron_write and return a serialized result."""
        name = str(tool_call.get("name", "Scheduled task"))
        prompt = str(tool_call.get("prompt", ""))
        cron_expr = str(tool_call.get("cron_expr", ""))
        timezone_name = str(tool_call.get("timezone", "UTC"))
        if not self._user_uid:
            return "Cron tools require an authenticated user."
        try:
            from backend.automation import _compute_next_run, _validate_cron
            from backend.database import ScheduledTask, _session_factory

            if _session_factory is None:
                return "Database not ready."
            validated_expr = _validate_cron(cron_expr)
            next_run = _compute_next_run(validated_expr, timezone_name)
            async with _session_factory() as session:
                task = ScheduledTask(
                    user_id=self._user_uid,
                    name=name,
                    prompt=prompt,
                    cron_expr=validated_expr,
                    timezone=timezone_name,
                    enabled=True,
                    next_run_at=next_run,
                    last_status="pending",
                    run_count=0,
                )
                session.add(task)
                await session.commit()
                await session.refresh(task)
                return _json_result({"ok": True, "task_id": task.id, "next_run_at": str(task.next_run_at)})
        except Exception as exc:  # noqa: BLE001
            return f"cron_write error: {exc}"

    async def _cron_patch(self, tool_call: dict[str, Any]) -> str:
        """Execute cron_patch and return a serialized result."""
        task_id = str(tool_call.get("task_id", ""))
        if not self._user_uid:
            return "Cron tools require an authenticated user."
        try:
            from backend.automation import _compute_next_run, _validate_cron
            from backend.database import ScheduledTask, _session_factory

            if _session_factory is None:
                return "Database not ready."
            async with _session_factory() as session:
                task = await session.get(ScheduledTask, task_id)
                if not task or task.user_id != self._user_uid:
                    return f"Cron task {task_id} not found."
                if "name" in tool_call:
                    task.name = str(tool_call["name"])
                if "prompt" in tool_call:
                    task.prompt = str(tool_call["prompt"])
                if "enabled" in tool_call:
                    task.enabled = bool(tool_call["enabled"])
                if "timezone" in tool_call:
                    task.timezone = str(tool_call["timezone"])
                if "cron_expr" in tool_call:
                    task.cron_expr = _validate_cron(str(tool_call["cron_expr"]))
                task.next_run_at = _compute_next_run(task.cron_expr, task.timezone)
                await session.commit()
                return _json_result({"ok": True, "task_id": task_id, "next_run_at": str(task.next_run_at)})
        except Exception as exc:  # noqa: BLE001
            return f"cron_patch error: {exc}"

    async def _cron_delete(self, tool_call: dict[str, Any]) -> str:
        """Execute cron_delete and return a serialized result."""
        task_id = str(tool_call.get("task_id", ""))
        if not self._user_uid:
            return "Cron tools require an authenticated user."
        try:
            from backend.database import ScheduledTask, _session_factory

            if _session_factory is None:
                return "Database not ready."
            async with _session_factory() as session:
                task = await session.get(ScheduledTask, task_id)
                if not task or task.user_id != self._user_uid:
                    return f"Cron task {task_id} not found."
                await session.delete(task)
                await session.commit()
                return _json_result({"ok": True, "task_id": task_id})
        except Exception as exc:  # noqa: BLE001
            return f"cron_delete error: {exc}"


def _extract_first_json_object(text: str) -> str | None:
    """Return the first balanced JSON object found in free-form model output."""
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if start is None:
            if char == "{":
                start = index
                depth = 1
                in_string = False
                escaped = False
            continue

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def _parse_tool_call(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from model output."""
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL | re.IGNORECASE)
    candidates = [fenced.group(1)] if fenced else []
    candidates.append(stripped)

    for candidate in candidates:
        payload = _extract_first_json_object(candidate)
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


async def run_universal_navigation(
    *,
    provider: BaseProvider,
    model: str,
    executor: Any,
    session_id: str,
    instruction: str,
    settings: dict[str, Any] | None = None,
    on_step: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    on_frame: Callable[[str], Awaitable[None]] | None = None,
    cancel_event: asyncio.Event | None = None,
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
    """Run a vision+tool-calling navigation loop with any BaseProvider."""
    resolved_settings = settings or {}
    tool_executor = UniversalToolExecutor(
        executor,
        session_id=session_id,
        settings=resolved_settings,
        user_uid=user_uid,
        on_user_input=on_user_input,
        on_spawn_subagent=on_spawn_subagent,
        on_message_subagent=on_message_subagent,
        is_subagent=is_subagent,
    )
    runtime_skills_section, included_skills, excluded_skills = await _load_runtime_skills(
        session_id=session_id,
        user_uid=user_uid,
        settings=resolved_settings,
    )
    skills_loaded_event = {
        "type": "skills_loaded",
        "task_id": session_id,
        "skills": included_skills,
        "excluded": excluded_skills,
    }
    logger.info("skills_loaded %s", json.dumps(skills_loaded_event, ensure_ascii=False))
    if on_workflow_step:
        await on_workflow_step(skills_loaded_event)

    system_prompt = await _build_system_prompt(
        session_id=session_id,
        settings=resolved_settings,
        is_subagent=is_subagent,
        runtime_skills_section=runtime_skills_section,
    )
    messages: list[ChatMessage] = []
    steps: list[dict[str, Any]] = []
    parent_step_id: str | None = None
    total_input_tokens = 0
    total_output_tokens = 0

    async def emit_step(content: str, step_type: str = "step") -> None:
        step_data = {"type": step_type, "content": content, "steering": []}
        steps.append(step_data)
        if on_step:
            await on_step(step_data)
        step_id = str(uuid4())
        if on_workflow_step:
            await on_workflow_step(
                {
                    "step_id": step_id,
                    "parent_step_id": parent_step_id,
                    "action": step_type,
                    "description": content[:200],
                    "status": "completed",
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "duration_ms": 300,
                    "screenshot": None,
                }
            )

    await emit_step(f"Starting task: {instruction}")

    messages.append(ChatMessage(role="system", content=system_prompt))
    if any(tool["name"] == "screenshot" for tool in _available_tools(resolved_settings, is_subagent=is_subagent)):
        kickoff = (
            f"Task: {instruction}\n\n"
            "If this task depends on the live browser page, start with a screenshot. "
            "If this is a repo, file, or API task and the browser is not needed yet, use the relevant enabled tools first."
        )
    else:
        kickoff = f"Task: {instruction}"
    messages.append(ChatMessage(role="user", content=kickoff))

    for step_num in range(MAX_STEPS):
        if cancel_event and cancel_event.is_set():
            return {"status": "interrupted", "instruction": instruction, "steps": steps}

        if steering_context:
            notes = steering_context.copy()
            steering_context.clear()
            steer_text = "User steering note: " + "; ".join(notes)
            messages.append(ChatMessage(role="user", content=steer_text))
            await emit_step(steer_text, step_type="steer")

        try:
            reply_parts: list[str] = []
            reasoning_parts: list[str] = []
            thinking_step_id = str(uuid4())

            if enable_reasoning and on_step:
                await on_step({"type": "reasoning_start", "step_id": thinking_step_id, "content": "[thinking]", "steering": []})

            effort_budgets = {"low": 2000, "medium": 8000, "high": 16000}
            reasoning_budget = effort_budgets.get(reasoning_effort, 8000)
            stream_kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": 1024,
                "enable_reasoning": enable_reasoning,
                "reasoning_effort": reasoning_effort,
                "reasoning_budget": reasoning_budget,
            }
            if not enable_reasoning:
                stream_kwargs["temperature"] = 0.2
            async for chunk in provider.stream(messages, **stream_kwargs):
                if cancel_event and cancel_event.is_set():
                    break
                if chunk.reasoning_delta:
                    reasoning_parts.append(chunk.reasoning_delta)
                    if on_reasoning_delta:
                        await on_reasoning_delta(thinking_step_id, chunk.reasoning_delta)
                if chunk.delta:
                    reply_parts.append(chunk.delta)

            reply = "".join(reply_parts).strip()
            if reasoning_parts and on_step:
                await on_step(
                    {
                        "type": "reasoning",
                        "step_id": thinking_step_id,
                        "content": f"[reasoning] {''.join(reasoning_parts)}",
                        "steering": [],
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM stream failed at step %d", step_num)
            return {
                "status": "failed",
                "instruction": instruction,
                "steps": steps,
                "error": str(exc),
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
            }

        messages.append(ChatMessage(role="assistant", content=reply))
        tool_call = _parse_tool_call(reply)
        if not tool_call:
            await emit_step(f"Model response (no tool call): {reply[:200]}")
            messages.append(ChatMessage(role="user", content="Please return exactly one JSON tool call to continue."))
            continue

        tool_name = str(tool_call.get("tool", "unknown"))
        if tool_name == "done":
            summary = str(tool_call.get("summary", "Task completed."))
            await emit_step(summary, step_type="result")
            return {
                "status": "completed",
                "instruction": instruction,
                "steps": steps,
                "summary": summary,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
            }
        if tool_name == "error":
            error_message = str(tool_call.get("message", "Unknown error."))
            await emit_step(f"Error: {error_message}", step_type="error")
            return {
                "status": "failed",
                "instruction": instruction,
                "steps": steps,
                "error": error_message,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
            }

        if tool_name == "ask_user_input":
            question = str(tool_call.get("question", ""))
            options = [str(item) for item in list(tool_call.get("options", []))]
            request_id = str(uuid4())
            special_step: dict[str, Any] = {
                "type": "user_input_request",
                "content": f"[ask_user_input] {question}",
                "question": question,
                "options": options,
                "request_id": request_id,
                "steering": [],
            }
            steps.append(special_step)
            if on_step:
                await on_step(special_step)
        else:
            await emit_step(f"[{tool_name}] {json.dumps({key: value for key, value in tool_call.items() if key != 'tool'})[:220]}")

        result_text, screenshot_bytes = await tool_executor.run(tool_call)
        if screenshot_bytes and on_frame:
            await on_frame(base64.b64encode(screenshot_bytes).decode())

        if screenshot_bytes:
            follow_up = ChatMessage(
                role="user",
                content=f"Tool result: {result_text}\nHere is the current screenshot. Decide your next action.",
                images=[screenshot_bytes],
            )
        else:
            follow_up = ChatMessage(role="user", content=f"Tool result: {result_text}\nDecide your next action.")
        messages.append(follow_up)

    await emit_step("Reached maximum step limit without completing task.", step_type="error")
    return {
        "status": "failed",
        "instruction": instruction,
        "steps": steps,
        "error": "Max steps reached",
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }
