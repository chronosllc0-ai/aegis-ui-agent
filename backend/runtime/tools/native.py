"""OpenAI Agents SDK wrappers for the legacy native tool catalog.

Every non-terminal, non-browser tool in ``universal_navigator.py``'s
``TOOL_DEFINITIONS`` manifest is re-exposed here as a
``@function_tool``. Tool names, parameter names, and result shapes
match the legacy contract so downstream consumers (prompts, training
data, docs, tests) keep working.

Out of scope for Phase 2:

* **Browser tools** (``screenshot``, ``go_to_url``, ``click``,
  ``type_text``, ``scroll``, ``go_back``, ``wait``) — Phase 3 wires
  these via Playwright / Browser MCP. They stay in the legacy manifest
  until then.
* **Terminal tools** (``done``, ``error``) — the Agents SDK treats the
  agent's ``final_output`` as the "done" signal; errors propagate as
  exceptions through the runner.

Implementation strategy:

* Reuse existing module-level helpers from
  :mod:`backend.session_workspace`, :mod:`backend.user_memory`,
  :mod:`backend.database`, and :mod:`backend.github_repo_workspace`
  verbatim. Do not duplicate business logic.
* Free functions + ``@function_tool`` only — no class instance. The
  :class:`~backend.runtime.tools.context.ToolContext` carries the small
  amount of per-run state every tool needs.
* Return value shapes mirror the legacy ``_json_result`` / plain-string
  contracts. The Agents SDK JSON-serializes anything non-string.

The module is safe to import even when optional deps (Postgres,
connectors) are missing — each tool guards its own imports inside the
body so the manifest stays available on every runtime.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from agents import RunContextWrapper, function_tool

from backend.runtime.tools.context import ToolContext
from backend.session_workspace import (
    get_session_workspace_root,
    resolve_session_path,
)
from backend.user_memory import (
    add_automation as _add_automation,
    append_daily_memory,
    compact_daily_memory,
    list_automations_for_session,
    patch_memory as _patch_memory,
    read_memory as _read_memory,
    remove_automation as _remove_automation,
    search_memory_files,
    write_memory as _write_memory,
)

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Shared helpers (mirror the ones in universal_navigator.py).
# ----------------------------------------------------------------------

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


def _truncate(text: str, limit: int = RESULT_CHAR_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n\n[truncated {len(text) - limit} characters]"


def _json_result(payload: Any) -> str:
    return _truncate(json.dumps(payload, ensure_ascii=False, indent=2))


def _strip_html(markup: str) -> str:
    without_scripts = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", " ", markup, flags=re.IGNORECASE | re.DOTALL
    )
    no_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def _canonical_integration_id(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "github":
        return "github-pat"
    return normalized


def _resolve_github_token(settings: dict[str, Any]) -> str:
    for raw in settings.get("integrations", []) or []:
        if not isinstance(raw, dict):
            continue
        integration_id = _canonical_integration_id(str(raw.get("id", "")))
        if integration_id != "github-pat":
            continue
        config = raw.get("settings", {}) or {}
        token = str(config.get("token", "")).strip()
        if token:
            return token
    return ""


async def _github_manager(ctx: ToolContext):
    """Return a GitHubRepoWorkspaceManager for the session, lazily."""
    from backend.github_repo_workspace import GitHubRepoWorkspaceManager

    cache_key = "__github_manager__"
    cached = ctx.extras.get(cache_key)
    if cached is not None:
        return cached
    token = _resolve_github_token(ctx.settings)
    if not token:
        raise RuntimeError("No connected GitHub PAT token is available in this session.")
    manager = GitHubRepoWorkspaceManager(session_id=ctx.session_id, token=token)
    await manager.ensure_identity()
    ctx.extras[cache_key] = manager
    return manager


# ----------------------------------------------------------------------
# web / extraction
# ----------------------------------------------------------------------


async def _web_search_impl(query: str, count: int) -> list[dict[str, str]]:
    from config import settings as _app_settings

    if getattr(_app_settings, "BRAVE_SEARCH_API_KEY", ""):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": count},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": _app_settings.BRAVE_SEARCH_API_KEY,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            return [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("description", ""),
                }
                for item in data.get("web", {}).get("results", [])
            ]
        except Exception as exc:  # noqa: BLE001 - best-effort; fall through
            logger.warning("Brave Search failed for %r — falling back: %s", query, exc)
    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 Aegis"},
    ) as client:
        response = await client.get("https://html.duckduckgo.com/html/", params={"q": query})
        response.raise_for_status()
    results: list[dict[str, str]] = []
    for match in re.finditer(
        r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        response.text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        url = html.unescape(match.group("url"))
        title = _strip_html(match.group("title"))
        rest = response.text[match.end() : match.end() + 1600]
        snippet_match = re.search(
            r'class="result__snippet"[^>]*>(?P<snippet>.*?)</(?:a|div)>',
            rest,
            flags=re.IGNORECASE | re.DOTALL,
        )
        snippet = _strip_html(snippet_match.group("snippet")) if snippet_match else ""
        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= count:
            break
    return results


@function_tool
async def web_search(
    ctx: RunContextWrapper[ToolContext], query: str, count: int = 5
) -> str:
    """Search the public web and return ranked results.

    Args:
        query: Free-text search query.
        count: Max results to return (1-10).
    """
    query = query.strip()
    count = min(max(count, 1), 10)
    if not query:
        return "web_search error: query is required."
    results = await _web_search_impl(query, count)
    return _json_result({"ok": True, "query": query, "results": results})


@function_tool
async def extract_page(ctx: RunContextWrapper[ToolContext], url: str) -> str:
    """Fetch a URL and return its title plus cleaned text content."""
    url = url.strip()
    if not url:
        return "extract_page error: url is required."
    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 Aegis"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
    title_match = re.search(
        r"<title[^>]*>(.*?)</title>", response.text, flags=re.IGNORECASE | re.DOTALL
    )
    title = _strip_html(title_match.group(1)) if title_match else ""
    content = _truncate(_strip_html(response.text), limit=5000)
    return _json_result(
        {"ok": True, "url": str(response.url), "title": title, "content": content}
    )


# ----------------------------------------------------------------------
# workspace files
# ----------------------------------------------------------------------


def _format_path_entry(path: Path, base: Path) -> dict[str, Any]:
    stat = path.stat()
    relative = path.relative_to(base)
    return {
        "path": str(relative) if str(relative) != "." else path.name,
        "type": "dir" if path.is_dir() else "file",
        "size": stat.st_size,
    }


@function_tool
async def list_files(
    ctx: RunContextWrapper[ToolContext],
    path: str = ".",
    recursive: bool = False,
    max_depth: int = 2,
) -> str:
    """List files or directories inside the current session workspace."""
    session_id = ctx.context.session_id
    root = resolve_session_path(session_id, path)
    if not root.exists():
        return "list_files error: path does not exist."
    if root.is_file():
        return _json_result(
            {
                "ok": True,
                "path": str(root),
                "entries": [_format_path_entry(root, base=root.parent)],
            }
        )
    entries: list[dict[str, Any]] = []
    max_depth = min(max(max_depth, 0), 6)
    base_depth = len(root.parts)
    iterator = root.rglob("*") if recursive else root.iterdir()
    for item in iterator:
        current_depth = len(item.parts) - base_depth
        if current_depth > max_depth:
            continue
        entries.append(_format_path_entry(item, base=root))
        if len(entries) >= 200:
            break
    entries.sort(key=lambda item: (item["type"] != "dir", item["path"]))
    return _json_result({"ok": True, "path": str(root), "entries": entries})


@function_tool
async def read_file(
    ctx: RunContextWrapper[ToolContext],
    path: str,
    start_line: int = 1,
    max_lines: int = 200,
) -> str:
    """Read a UTF-8 text file from the current session workspace."""
    if not path.strip():
        return "read_file error: path is required."
    file_path = resolve_session_path(ctx.context.session_id, path)
    if not file_path.exists() or not file_path.is_file():
        return "read_file error: file does not exist."
    start_line = max(start_line, 1)
    max_lines = min(max(max_lines, 1), 800)
    text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    start_index = max(start_line - 1, 0)
    end_index = min(start_index + max_lines, len(lines))
    excerpt = "\n".join(lines[start_index:end_index])
    return _json_result(
        {
            "ok": True,
            "path": str(file_path),
            "start_line": start_line,
            "end_line": end_index,
            "total_lines": len(lines),
            "content": _truncate(excerpt),
        }
    )


@function_tool
async def write_file(
    ctx: RunContextWrapper[ToolContext], path: str, content: str
) -> str:
    """Create or overwrite a UTF-8 text file inside the session workspace."""
    if not path.strip():
        return "write_file error: path is required."
    file_path = resolve_session_path(ctx.context.session_id, path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return _json_result(
        {"ok": True, "path": str(file_path), "bytes_written": len(content.encode("utf-8"))}
    )


# ----------------------------------------------------------------------
# code execution
# ----------------------------------------------------------------------


async def _run_interpreter(
    ctx: ToolContext,
    *,
    interpreter: str,
    suffix: str,
    code: str,
    cwd: str,
    filename: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    session_id = ctx.session_id
    cwd = cwd.strip() or "."
    cwd_path = resolve_session_path(session_id, cwd)
    workdir = cwd_path if cwd_path.is_dir() else cwd_path.parent
    workdir.mkdir(parents=True, exist_ok=True)
    fname = filename or f"aegis_exec_{uuid4().hex}{suffix}"
    script_raw = Path(fname) if Path(fname).is_absolute() else Path(cwd) / fname
    script_path = resolve_session_path(session_id, str(script_raw))
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(code, encoding="utf-8")
    timeout = min(max(int(timeout_seconds), 1), 120)
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(key.upper().startswith(prefix) for prefix in EXEC_ENV_BLOCKED_PREFIXES)
    }
    env.setdefault("HOME", str(get_session_workspace_root(session_id)))
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
        raise RuntimeError(
            f"{interpreter} execution timed out after {timeout} seconds"
        ) from exc
    return {
        "ok": process.returncode == 0,
        "cwd": str(workdir),
        "script_path": str(script_path),
        "return_code": process.returncode,
        "stdout": _truncate(stdout.decode("utf-8", errors="replace"), CODE_OUTPUT_LIMIT),
        "stderr": _truncate(stderr.decode("utf-8", errors="replace"), CODE_OUTPUT_LIMIT),
    }


@function_tool
async def exec_python(
    ctx: RunContextWrapper[ToolContext],
    code: str,
    cwd: str = ".",
    timeout_seconds: int = 30,
    filename: str | None = None,
) -> str:
    """Run Python code inside the current session workspace."""
    if not code.strip():
        return "exec_python error: code is required."
    result = await _run_interpreter(
        ctx.context,
        interpreter="python",
        suffix=".py",
        code=code,
        cwd=cwd,
        filename=filename,
        timeout_seconds=timeout_seconds,
    )
    return _json_result(result)


@function_tool
async def exec_javascript(
    ctx: RunContextWrapper[ToolContext],
    code: str,
    cwd: str = ".",
    timeout_seconds: int = 30,
    filename: str | None = None,
) -> str:
    """Run Node.js JavaScript inside the current session workspace."""
    if not code.strip():
        return "exec_javascript error: code is required."
    result = await _run_interpreter(
        ctx.context,
        interpreter="node",
        suffix=".mjs",
        code=code,
        cwd=cwd,
        filename=filename,
        timeout_seconds=timeout_seconds,
    )
    return _json_result(result)


@function_tool
async def exec_shell(
    ctx: RunContextWrapper[ToolContext],
    command: str,
    cwd: str = ".",
    timeout_seconds: int = 60,
) -> str:
    """Run a shell command inside the current session workspace sandbox."""
    command = command.strip()
    if not command:
        return "exec_shell error: command is required."
    session_id = ctx.context.session_id
    cwd_str = cwd.strip() or "."
    cwd_path = resolve_session_path(session_id, cwd_str)
    workdir = cwd_path if cwd_path.is_dir() else cwd_path.parent
    workdir.mkdir(parents=True, exist_ok=True)
    timeout = min(max(int(timeout_seconds), 1), 180)
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(key.upper().startswith(prefix) for prefix in EXEC_ENV_BLOCKED_PREFIXES)
    }
    env.setdefault("HOME", str(get_session_workspace_root(session_id)))
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
        return _json_result(
            {"ok": False, "error": f"shell command timed out after {timeout} seconds"}
        )
    return _json_result(
        {
            "ok": process.returncode == 0,
            "cwd": str(workdir),
            "command": command,
            "return_code": process.returncode,
            "stdout": _truncate(stdout.decode("utf-8", errors="replace"), CODE_OUTPUT_LIMIT),
            "stderr": _truncate(stderr.decode("utf-8", errors="replace"), CODE_OUTPUT_LIMIT),
        }
    )


# ----------------------------------------------------------------------
# flow control: ask_user_input, handoff_to_user, summarize_task, confirm_plan
# ----------------------------------------------------------------------


@function_tool
async def ask_user_input(
    ctx: RunContextWrapper[ToolContext],
    question: str,
    options: list[str] | None = None,
) -> str:
    """Pause execution and ask the user a clarifying question."""
    question = question.strip()
    if not question:
        return "ask_user_input error: question is required."
    opts = [str(item) for item in (options or [])][:4]
    handler = ctx.context.on_ask_user_input
    if handler is None:
        return "ask_user_input error: no user-input handler is available in this run."
    try:
        answer = await handler(question, opts)
    except Exception as exc:  # noqa: BLE001
        return f"ask_user_input error: {exc}"
    return f"User answered: {answer}"


@function_tool
async def handoff_to_user(
    ctx: RunContextWrapper[ToolContext],
    reason: str,
    instructions: str,
    continue_label: str | None = None,
) -> str:
    """Pause execution and hand browser control to the human.

    Used for CAPTCHA / auth / manual unblock steps.
    """
    reason = reason.strip()
    instructions = instructions.strip()
    if not reason or not instructions:
        return "handoff_to_user error: reason and instructions are required."
    handler = ctx.context.on_handoff_to_user
    if handler is None:
        return "handoff_to_user error: no handoff handler is available in this run."
    request_id = uuid4().hex
    if ctx.context.on_step is not None:
        try:
            await ctx.context.on_step(
                {
                    "type": "handoff_request",
                    "content": f"[handoff_to_user] {reason}",
                    "reason": reason,
                    "instructions": instructions,
                    "continue_label": continue_label,
                    "request_id": request_id,
                    "steering": [],
                }
            )
        except Exception:  # noqa: BLE001
            logger.exception("handoff_to_user step emit failed")
    try:
        resume_text = await handler(reason, instructions, continue_label, request_id)
    except Exception as exc:  # noqa: BLE001
        return f"handoff_to_user error: {exc}"
    return resume_text or "Human handoff completed. Resuming agent."


@function_tool
async def summarize_task(
    ctx: RunContextWrapper[ToolContext],
    content: str,
    max_sentences: int = 4,
) -> str:
    """Condense notes into a short summary."""
    max_sentences = min(max(max_sentences, 1), 10)
    if not content:
        return _json_result({"ok": True, "summary": ""})
    sentences = [
        segment.strip()
        for segment in re.split(r"(?<=[.!?])\s+", content)
        if segment.strip()
    ]
    summary = (
        _truncate(content, 600) if not sentences else " ".join(sentences[:max_sentences])
    )
    return _json_result({"ok": True, "summary": summary})


@function_tool
async def confirm_plan(
    ctx: RunContextWrapper[ToolContext],
    plan: list[str] | str,
) -> str:
    """Show a proposed plan to the user and wait for approval."""
    handler = ctx.context.on_ask_user_input
    if handler is None:
        return "confirm_plan error: no user approval handler is available in this run."
    if isinstance(plan, list):
        plan_text = "\n".join(f"- {str(item)}" for item in plan)
    else:
        plan_text = str(plan).strip()
    try:
        answer = await handler(
            f"Approve this plan?\n{plan_text}",
            ["Approve", "Revise", "Cancel"],
        )
    except Exception as exc:  # noqa: BLE001
        return f"confirm_plan error: {exc}"
    return _json_result({"ok": True, "response": answer})


# ----------------------------------------------------------------------
# memory v2 (DB-backed)
# ----------------------------------------------------------------------


def _require_uid(ctx: ToolContext, tool_label: str) -> str | None:
    if not ctx.owner_uid:
        return f"{tool_label} error: an authenticated user is required."
    return None


@function_tool
async def memory_search(ctx: RunContextWrapper[ToolContext], query: str) -> str:
    """Semantic search through stored memories (DB + file fallback)."""
    c = ctx.context
    query = query.strip()
    if not query:
        return "memory_search error: query is required."
    if c.memory_mode in {"db", "hybrid"} and not c.owner_uid:
        return "memory_search error: an authenticated user is required."
    try:
        db_results: list[dict[str, Any]] = []
        file_results: list[dict[str, str]] = []
        if c.memory_mode in {"db", "hybrid"}:
            from backend.database import _session_factory
            from backend.memory.service import MemoryService

            if _session_factory is None:
                if c.memory_mode == "db":
                    return "memory_search error: database not ready."
            else:
                async with _session_factory() as session:
                    db_results = await MemoryService.recall(
                        session, c.owner_uid, query, limit=5
                    )
        if c.memory_mode in {"files", "hybrid"}:
            file_results = search_memory_files(
                c.session_id,
                query,
                include_long_term=c.should_include_long_term_memory(),
                limit=5,
            )
        return _json_result(
            {
                "ok": True,
                "mode": c.memory_mode,
                "db_results": db_results,
                "file_results": file_results,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return f"memory_search error: {exc}"


@function_tool
async def memory_write(
    ctx: RunContextWrapper[ToolContext],
    content: str,
    category: str = "general",
) -> str:
    """Store a new memory entry."""
    c = ctx.context
    content = content.strip()
    if not content:
        return "memory_write error: content is required."
    if c.memory_mode in {"db", "hybrid"} and not c.owner_uid:
        return "memory_write error: an authenticated user is required."
    try:
        entry: dict[str, Any] | None = None
        written_day: str | None = None
        if c.memory_mode in {"db", "hybrid"}:
            from backend.database import _session_factory
            from backend.memory.service import MemoryService

            if _session_factory is None:
                if c.memory_mode == "db":
                    return "memory_write error: database not ready."
            else:
                async with _session_factory() as session:
                    entry = await MemoryService.store(
                        session, c.owner_uid, content, category=category
                    )
        if c.memory_mode in {"files", "hybrid"}:
            written_day = append_daily_memory(c.session_id, content, category=category)
        return _json_result(
            {
                "ok": True,
                "mode": c.memory_mode,
                "entry": entry,
                "short_term_day": written_day,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return f"memory_write error: {exc}"


@function_tool
async def memory_read(ctx: RunContextWrapper[ToolContext], memory_id: str) -> str:
    """Read a specific memory entry by ID."""
    c = ctx.context
    if c.memory_mode == "files":
        return "memory_read is DB-only in files mode. Use read_memory for file-based memory."
    if not c.owner_uid:
        return "memory_read error: an authenticated user is required."
    try:
        from backend.database import _session_factory
        from backend.memory.service import MemoryService

        if _session_factory is None:
            return "memory_read error: database not ready."
        async with _session_factory() as session:
            entry = await MemoryService.get_memory(session, memory_id, c.owner_uid)
        if not entry:
            return f"Memory {memory_id} not found."
        return _json_result({"ok": True, "entry": entry})
    except Exception as exc:  # noqa: BLE001
        return f"memory_read error: {exc}"


@function_tool
async def memory_patch(
    ctx: RunContextWrapper[ToolContext],
    memory_id: str,
    content: str | None = None,
    category: str | None = None,
) -> str:
    """Update a specific memory entry."""
    c = ctx.context
    if c.memory_mode == "files":
        return "memory_patch is DB-only in files mode. Use patch_memory for MEMORY.md."
    if not c.owner_uid:
        return "memory_patch error: an authenticated user is required."
    try:
        from backend.database import _session_factory
        from backend.memory.service import MemoryService

        if _session_factory is None:
            return "memory_patch error: database not ready."
        async with _session_factory() as session:
            updated = await MemoryService.update_memory(
                session, memory_id, c.owner_uid, content=content, category=category
            )
        if not updated:
            return f"Memory {memory_id} not found or not updated."
        return _json_result({"ok": True, "memory_id": memory_id})
    except Exception as exc:  # noqa: BLE001
        return f"memory_patch error: {exc}"


# ----------------------------------------------------------------------
# cron (DB-backed scheduled tasks)
# ----------------------------------------------------------------------


@function_tool
async def cron_write(
    ctx: RunContextWrapper[ToolContext],
    name: str = "Scheduled task",
    prompt: str = "",
    cron_expr: str = "",
    timezone: str = "UTC",
) -> str:
    """Create a scheduled automation."""
    c = ctx.context
    guard = _require_uid(c, "cron_write")
    if guard:
        return guard
    try:
        from backend.automation import _compute_next_run, _validate_cron
        from backend.database import ScheduledTask, _session_factory

        if _session_factory is None:
            return "cron_write error: database not ready."
        validated_expr = _validate_cron(cron_expr)
        next_run = _compute_next_run(validated_expr, timezone)
        async with _session_factory() as session:
            task = ScheduledTask(
                user_id=c.owner_uid,
                name=name,
                prompt=prompt,
                cron_expr=validated_expr,
                timezone=timezone,
                enabled=True,
                next_run_at=next_run,
                last_status="pending",
                run_count=0,
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return _json_result(
                {"ok": True, "task_id": task.id, "next_run_at": str(task.next_run_at)}
            )
    except Exception as exc:  # noqa: BLE001
        return f"cron_write error: {exc}"


@function_tool
async def cron_patch(
    ctx: RunContextWrapper[ToolContext],
    task_id: str,
    name: str | None = None,
    prompt: str | None = None,
    enabled: bool | None = None,
    timezone: str | None = None,
    cron_expr: str | None = None,
) -> str:
    """Modify an existing scheduled automation."""
    c = ctx.context
    guard = _require_uid(c, "cron_patch")
    if guard:
        return guard
    try:
        from backend.automation import _compute_next_run, _validate_cron
        from backend.database import ScheduledTask, _session_factory

        if _session_factory is None:
            return "cron_patch error: database not ready."
        async with _session_factory() as session:
            task = await session.get(ScheduledTask, task_id)
            if not task or task.user_id != c.owner_uid:
                return f"Cron task {task_id} not found."
            if name is not None:
                task.name = name
            if prompt is not None:
                task.prompt = prompt
            if enabled is not None:
                task.enabled = bool(enabled)
            if timezone is not None:
                task.timezone = timezone
            if cron_expr is not None:
                task.cron_expr = _validate_cron(cron_expr)
            task.next_run_at = _compute_next_run(task.cron_expr, task.timezone)
            await session.commit()
            return _json_result(
                {"ok": True, "task_id": task_id, "next_run_at": str(task.next_run_at)}
            )
    except Exception as exc:  # noqa: BLE001
        return f"cron_patch error: {exc}"


@function_tool
async def cron_delete(ctx: RunContextWrapper[ToolContext], task_id: str) -> str:
    """Delete a scheduled automation."""
    c = ctx.context
    guard = _require_uid(c, "cron_delete")
    if guard:
        return guard
    try:
        from backend.database import ScheduledTask, _session_factory

        if _session_factory is None:
            return "cron_delete error: database not ready."
        async with _session_factory() as session:
            task = await session.get(ScheduledTask, task_id)
            if not task or task.user_id != c.owner_uid:
                return f"Cron task {task_id} not found."
            await session.delete(task)
            await session.commit()
            return _json_result({"ok": True, "task_id": task_id})
    except Exception as exc:  # noqa: BLE001
        return f"cron_delete error: {exc}"


# ----------------------------------------------------------------------
# legacy file-backed memory
# ----------------------------------------------------------------------


@function_tool
async def read_memory(ctx: RunContextWrapper[ToolContext]) -> str:
    """Read the user's memory file (preferences, facts, context)."""
    c = ctx.context
    return _read_memory(
        c.session_id, include_long_term=c.should_include_long_term_memory()
    )


@function_tool
async def write_memory(ctx: RunContextWrapper[ToolContext], content: str) -> str:
    """Overwrite the user's entire memory.md file."""
    _write_memory(ctx.context.session_id, content)
    return "Memory updated."


@function_tool
async def patch_memory(
    ctx: RunContextWrapper[ToolContext], section: str, content: str
) -> str:
    """Update or append a named section in the user's memory.md."""
    return _patch_memory(ctx.context.session_id, section, content)


@function_tool
async def compact_memory(
    ctx: RunContextWrapper[ToolContext],
    apply_to_long_term: bool = False,
    include_long_term_context: bool = True,
) -> str:
    """Summarize short-term daily memory into suggested MEMORY.md updates."""
    payload = compact_daily_memory(
        ctx.context.session_id,
        apply_to_long_term=apply_to_long_term,
        include_long_term_context=include_long_term_context,
    )
    return _json_result(payload)


# ----------------------------------------------------------------------
# automations (legacy per-session)
# ----------------------------------------------------------------------


@function_tool
async def add_automation(
    ctx: RunContextWrapper[ToolContext],
    task: str,
    schedule: str,
    label: str = "",
) -> str:
    """Schedule a recurring task for Aegis to run automatically."""
    auto = _add_automation(ctx.context.session_id, task, schedule, label)
    return f"Automation '{auto['label']}' scheduled. ID: {auto['id']}"


@function_tool
async def list_automations(ctx: RunContextWrapper[ToolContext]) -> str:
    """Show all scheduled automations for this session."""
    autos = list_automations_for_session(ctx.context.session_id)
    return json.dumps(autos, indent=2) if autos else "No automations configured."


@function_tool
async def remove_automation(
    ctx: RunContextWrapper[ToolContext], automation_id: str
) -> str:
    """Delete a scheduled automation by its ID."""
    ok = _remove_automation(ctx.context.session_id, automation_id)
    return "Automation removed." if ok else "Automation not found."


# ----------------------------------------------------------------------
# subagents
# ----------------------------------------------------------------------


_VALID_STEERING_PRIORITIES = frozenset({"low", "normal", "high", "urgent"})


def _apply_subagent_steering_priority(message: Any, priority: Any) -> str:
    msg = str(message or "").strip()
    pri = str(priority or "").strip().lower()
    if pri and pri in _VALID_STEERING_PRIORITIES and pri != "normal":
        return f"[priority:{pri}] {msg}" if msg else f"[priority:{pri}]"
    return msg


@function_tool
async def spawn_subagent(
    ctx: RunContextWrapper[ToolContext],
    instruction: str,
    model: str = "",
) -> str:
    """Spawn a focused sub-agent for parallel work."""
    c = ctx.context
    instruction = instruction.strip()
    if not instruction:
        return "spawn_subagent error: instruction is required."
    if c.on_spawn_subagent is None:
        return "spawn_subagent is not available in this context."
    try:
        sub_id = await c.on_spawn_subagent(instruction, model)
    except Exception as exc:  # noqa: BLE001
        return f"spawn_subagent error: {exc}"
    return f"Sub-agent spawned with id={sub_id}. It is now running independently."


@function_tool
async def message_subagent(
    ctx: RunContextWrapper[ToolContext],
    sub_id: str,
    message: str,
) -> str:
    """Send a steering update to a running sub-agent."""
    c = ctx.context
    sub_id = sub_id.strip()
    payload = _apply_subagent_steering_priority(message, "")
    if not sub_id or not payload:
        return "message_subagent error: sub_id and message are required."
    if c.on_message_subagent is None:
        return "message_subagent is not available in this context."
    try:
        ok = await c.on_message_subagent(sub_id, payload)
    except Exception as exc:  # noqa: BLE001
        return f"message_subagent error: {exc}"
    return f"Steering message {'sent' if ok else 'failed'} for sub-agent {sub_id}."


@function_tool
async def steer_subagent(
    ctx: RunContextWrapper[ToolContext],
    sub_id: str,
    message: str,
    priority: str = "",
) -> str:
    """Alias of message_subagent with optional priority metadata."""
    c = ctx.context
    sub_id = sub_id.strip()
    payload = _apply_subagent_steering_priority(message, priority)
    if not sub_id or not payload:
        return "steer_subagent error: sub_id and message are required."
    if c.on_message_subagent is None:
        return "steer_subagent is not available in this context."
    try:
        ok = await c.on_message_subagent(sub_id, payload)
    except Exception as exc:  # noqa: BLE001
        return f"steer_subagent error: {exc}"
    return f"Steering message {'sent' if ok else 'failed'} for sub-agent {sub_id}."


# ----------------------------------------------------------------------
# GitHub
# ----------------------------------------------------------------------


@function_tool
async def github_list_repos(
    ctx: RunContextWrapper[ToolContext], per_page: int = 30
) -> str:
    """List repositories available to the connected GitHub PAT."""
    per_page = min(max(int(per_page), 1), 100)
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(await gh.list_repos(per_page=per_page))
    except Exception as exc:  # noqa: BLE001
        return f"github_list_repos error: {exc}"


@function_tool
async def github_get_issues(
    ctx: RunContextWrapper[ToolContext], repo: str, state: str = "open"
) -> str:
    """List issues in a GitHub repository."""
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(await gh.get_issues(repo.strip(), state=state))
    except Exception as exc:  # noqa: BLE001
        return f"github_get_issues error: {exc}"


@function_tool
async def github_create_issue(
    ctx: RunContextWrapper[ToolContext], repo: str, title: str, body: str = ""
) -> str:
    """Create a GitHub issue."""
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(
            await gh.create_issue(repo.strip(), title.strip(), body)
        )
    except Exception as exc:  # noqa: BLE001
        return f"github_create_issue error: {exc}"


@function_tool
async def github_get_pull_requests(
    ctx: RunContextWrapper[ToolContext], repo: str, state: str = "open"
) -> str:
    """List pull requests in a GitHub repository."""
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(await gh.get_pull_requests(repo.strip(), state=state))
    except Exception as exc:  # noqa: BLE001
        return f"github_get_pull_requests error: {exc}"


@function_tool
async def github_create_comment(
    ctx: RunContextWrapper[ToolContext],
    repo: str,
    issue_number: int,
    body: str,
) -> str:
    """Create a GitHub issue or PR comment."""
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(
            await gh.create_comment(repo.strip(), int(issue_number), body)
        )
    except Exception as exc:  # noqa: BLE001
        return f"github_create_comment error: {exc}"


@function_tool
async def github_get_file(
    ctx: RunContextWrapper[ToolContext],
    repo: str,
    path: str,
    ref: str | None = None,
) -> str:
    """Read a file directly from a GitHub repository via the API."""
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(
            await gh.get_file(
                repo.strip(), path.strip(), ref=(ref.strip() or None) if ref else None
            )
        )
    except Exception as exc:  # noqa: BLE001
        return f"github_get_file error: {exc}"


@function_tool
async def github_clone_repo(
    ctx: RunContextWrapper[ToolContext],
    repo: str,
    ref: str | None = None,
) -> str:
    """Clone a GitHub repository into the session workspace."""
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(
            await gh.clone_repo(repo.strip(), ref=(ref.strip() or None) if ref else None)
        )
    except Exception as exc:  # noqa: BLE001
        return f"github_clone_repo error: {exc}"


@function_tool
async def github_create_branch(
    ctx: RunContextWrapper[ToolContext],
    local_path: str,
    branch_name: str,
    base_ref: str | None = None,
) -> str:
    """Create or reset a local branch inside a cloned repository."""
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(
            await gh.create_branch(
                local_path.strip(),
                branch_name.strip(),
                base_ref=(base_ref.strip() or None) if base_ref else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return f"github_create_branch error: {exc}"


@function_tool
async def github_repo_status(
    ctx: RunContextWrapper[ToolContext], local_path: str
) -> str:
    """Inspect local git status for a cloned repository."""
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(await gh.repo_status(local_path.strip()))
    except Exception as exc:  # noqa: BLE001
        return f"github_repo_status error: {exc}"


@function_tool
async def github_repo_diff(
    ctx: RunContextWrapper[ToolContext],
    local_path: str,
    staged: bool = False,
    pathspec: str | None = None,
) -> str:
    """Read the local git diff for a cloned repository."""
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(
            await gh.repo_diff(
                local_path.strip(),
                staged=bool(staged),
                pathspec=(pathspec.strip() or None) if pathspec else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return f"github_repo_diff error: {exc}"


@function_tool
async def github_commit_changes(
    ctx: RunContextWrapper[ToolContext],
    local_path: str,
    message: str,
) -> str:
    """Stage all local changes in a cloned repository and create a commit."""
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(
            await gh.commit_changes(local_path.strip(), message.strip())
        )
    except Exception as exc:  # noqa: BLE001
        return f"github_commit_changes error: {exc}"


@function_tool
async def github_push_branch(
    ctx: RunContextWrapper[ToolContext],
    local_path: str,
    branch: str | None = None,
) -> str:
    """Push the current branch of a cloned repository back to GitHub."""
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(
            await gh.push_branch(
                local_path.strip(),
                branch=(branch.strip() or None) if branch else None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return f"github_push_branch error: {exc}"


@function_tool
async def github_create_pull_request(
    ctx: RunContextWrapper[ToolContext],
    local_path: str,
    title: str,
    body: str,
    base: str = "main",
    head: str | None = None,
    draft: bool = False,
) -> str:
    """Open a pull request from the cloned repository using GitHub CLI."""
    try:
        gh = await _github_manager(ctx.context)
        return _json_result(
            await gh.create_pull_request(
                local_path.strip(),
                title.strip(),
                body,
                base=(base.strip() or "main"),
                head=(head.strip() or None) if head else None,
                draft=bool(draft),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return f"github_create_pull_request error: {exc}"


# ----------------------------------------------------------------------
# Public manifest
# ----------------------------------------------------------------------


NATIVE_TOOLS = [
    # web / extraction
    web_search,
    extract_page,
    # workspace files
    list_files,
    read_file,
    write_file,
    # code exec
    exec_python,
    exec_javascript,
    exec_shell,
    # flow control
    ask_user_input,
    handoff_to_user,
    summarize_task,
    confirm_plan,
    # memory v2 (DB)
    memory_search,
    memory_write,
    memory_read,
    memory_patch,
    # cron
    cron_write,
    cron_patch,
    cron_delete,
    # memory legacy (file)
    read_memory,
    write_memory,
    patch_memory,
    compact_memory,
    # automations
    add_automation,
    list_automations,
    remove_automation,
    # subagents
    spawn_subagent,
    message_subagent,
    steer_subagent,
    # github
    github_list_repos,
    github_get_issues,
    github_create_issue,
    github_get_pull_requests,
    github_create_comment,
    github_get_file,
    github_clone_repo,
    github_create_branch,
    github_repo_status,
    github_repo_diff,
    github_commit_changes,
    github_push_branch,
    github_create_pull_request,
]
"""All non-terminal native tools, ready to hand to :class:`agents.Agent`."""


NATIVE_TOOL_NAMES: frozenset[str] = frozenset(t.name for t in NATIVE_TOOLS)
"""Name lookup for tests / integration wiring."""

__all__ = [
    "NATIVE_TOOLS",
    "NATIVE_TOOL_NAMES",
    "ToolContext",
]
