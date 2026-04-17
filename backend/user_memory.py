"""Per-user persistent memory and automation storage for Aegis.

Files per session:
  /data/users/{session_id}/MEMORY.md          — Curated long-term memory
  /data/users/{session_id}/memory/YYYY-MM-DD.md — Daily short-term memory
  /data/users/{session_id}/heartbeat.md       — Human-readable automation schedule
  /data/users/{session_id}/automations.json   — Structured automation configs
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None

USER_DATA_ROOT = Path(os.environ.get("USER_DATA_ROOT", "/data/users"))
LONG_TERM_MEMORY_FILE = "MEMORY.md"
LEGACY_LONG_TERM_MEMORY_FILE = "memory.md"
SHORT_TERM_MEMORY_DIR = "memory"


def _user_dir(session_id: str) -> Path:
    d = USER_DATA_ROOT / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _normalize_day(day: str | None = None) -> str:
    if day:
        return str(day)
    return datetime.now(timezone.utc).date().isoformat()


def _short_term_dir(session_id: str) -> Path:
    d = _user_dir(session_id) / SHORT_TERM_MEMORY_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _daily_memory_path(session_id: str, day: str | None = None) -> Path:
    normalized_day = _normalize_day(day)
    return _short_term_dir(session_id) / f"{normalized_day}.md"


def ensure_daily_memory_file(session_id: str, day: str | None = None) -> Path:
    """Ensure the daily short-term memory file exists and return its path."""
    target_day = _normalize_day(day)
    path = _daily_memory_path(session_id, target_day)
    if not path.exists():
        path.write_text(f"# Daily Memory {target_day}\n\n")
    return path


def _long_term_memory_path(session_id: str) -> Path:
    return _user_dir(session_id) / LONG_TERM_MEMORY_FILE


def _legacy_long_term_memory_path(session_id: str) -> Path:
    return _user_dir(session_id) / LEGACY_LONG_TERM_MEMORY_FILE


def read_long_term_memory(session_id: str) -> str:
    """Read long-term memory, migrating legacy lower-case file when needed."""
    current_path = _long_term_memory_path(session_id)
    if current_path.exists():
        return current_path.read_text()

    legacy_path = _legacy_long_term_memory_path(session_id)
    if legacy_path.exists():
        legacy_content = legacy_path.read_text()
        current_path.write_text(legacy_content)
        return legacy_content

    default = "# MEMORY\n\nCurated long-term memory is empty."
    current_path.write_text(default)
    return default


def write_long_term_memory(session_id: str, content: str) -> None:
    _long_term_memory_path(session_id).write_text(content)


def _recent_short_term_days(now: datetime | None = None) -> list[str]:
    reference = now or datetime.now(timezone.utc)
    today = reference.date()
    yesterday = today - timedelta(days=1)
    return [today.isoformat(), yesterday.isoformat()]


def read_recent_short_term_memory(session_id: str, now: datetime | None = None) -> dict[str, str]:
    """Read today + yesterday short-term memory files (auto-creating today)."""
    days = _recent_short_term_days(now)
    today_path = ensure_daily_memory_file(session_id, days[0])
    yesterday_path = _daily_memory_path(session_id, days[1])

    result: dict[str, str] = {days[0]: today_path.read_text()}
    if yesterday_path.exists():
        result[days[1]] = yesterday_path.read_text()
    else:
        result[days[1]] = f"# Daily Memory {days[1]}\n\n(no entries)"
    return result


def append_daily_memory(session_id: str, content: str, *, category: str = "general", day: str | None = None) -> str:
    """Append a timestamped entry to a daily short-term memory file."""
    normalized_day = _normalize_day(day)
    path = ensure_daily_memory_file(session_id, normalized_day)
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%SZ")
    entry = f"\n## [{timestamp}] {category}\n{content.strip()}\n"
    _append_text_atomic(path, entry + "\n")
    return normalized_day


def _append_text_atomic(path: Path, content: str) -> None:
    """Append text atomically to a file to prevent concurrent write clobbering."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def search_memory_files(
    session_id: str,
    query: str,
    *,
    include_long_term: bool = True,
    limit: int = 5,
) -> list[dict[str, str]]:
    """Run a lightweight text search across recent file-based memories."""
    needle = query.strip().lower()
    if not needle:
        return []

    results: list[dict[str, str]] = []
    recent = read_recent_short_term_memory(session_id)
    for day, content in recent.items():
        if needle in content.lower():
            results.append({"source": f"short-term:{day}", "content": content})

    if include_long_term:
        long_term = read_long_term_memory(session_id)
        if needle in long_term.lower():
            results.append({"source": "long-term:MEMORY.md", "content": long_term})

    return results[: max(limit, 1)]


def read_memory(session_id: str, *, include_long_term: bool = True) -> str:
    """Read short-term memory (today+yesterday) plus optional long-term memory."""
    days = _recent_short_term_days()
    short_term = read_recent_short_term_memory(session_id)
    today_day = days[0]
    yesterday_day = days[1]
    today_text = short_term.get(today_day, f"# Daily Memory {today_day}\n\n(no entries)")
    yesterday_text = short_term.get(yesterday_day, f"# Daily Memory {yesterday_day}\n\n(no entries)")
    sections = ["# Memory Context"]
    sections.append(f"\n## Today ({today_day})\n{today_text.strip()}")
    sections.append(f"\n## Yesterday ({yesterday_day})\n{yesterday_text.strip()}")
    if include_long_term:
        sections.append(f"\n## Long-term (MEMORY.md)\n{read_long_term_memory(session_id).strip()}")
    return "\n".join(sections).strip()


def write_memory(session_id: str, content: str) -> None:
    """Write curated long-term memory to MEMORY.md."""
    write_long_term_memory(session_id, content)


def patch_memory(session_id: str, section: str, content: str) -> str:
    """Update or append a named section in MEMORY.md. Returns new full content."""
    current = read_long_term_memory(session_id)
    header = f"## {section}"
    if header in current:
        pattern = rf"(## {re.escape(section)}\n)(.*?)(?=\n## |\Z)"
        replacement = rf"\g<1>{content}\n"
        updated = re.sub(pattern, replacement, current, flags=re.DOTALL)
    else:
        updated = current.rstrip() + f"\n\n## {section}\n{content}\n"
    write_long_term_memory(session_id, updated)
    return updated


def compact_daily_memory(
    session_id: str,
    *,
    apply_to_long_term: bool = False,
    include_long_term_context: bool = True,
) -> dict[str, Any]:
    """Build compaction suggestions from today+yesterday short-term memory.

    Returns a payload that can be manually accepted by applying `suggested_patch`
    to MEMORY.md. When `apply_to_long_term=True`, the patch is appended.
    """
    short_term = read_recent_short_term_memory(session_id)
    suggestion_lines: list[str] = []
    for day, content in short_term.items():
        entries = _extract_daily_entries(content)
        for entry in entries[:6]:
            suggestion_lines.append(f"- [{day}] {entry}")

    if not suggestion_lines:
        suggestion_lines = ["- No new short-term notes to compact."]

    suggested_patch = "## Compaction Suggestions\n" + "\n".join(suggestion_lines) + "\n"
    updated_long_term: str | None = None

    if apply_to_long_term:
        base = read_long_term_memory(session_id)
        updated_long_term = base.rstrip() + "\n\n" + suggested_patch
        write_long_term_memory(session_id, updated_long_term)

    payload: dict[str, Any] = {
        "ok": True,
        "applied": apply_to_long_term,
        "suggested_patch": suggested_patch,
        "short_term_days": list(short_term.keys()),
    }
    if include_long_term_context:
        payload["long_term_preview"] = read_long_term_memory(session_id)[:1500]
    if updated_long_term is not None:
        payload["updated_long_term"] = updated_long_term
    return payload


def _extract_daily_entries(content: str) -> list[str]:
    """Extract markdown section bodies from daily memory while preserving multiline entries."""
    entries: list[str] = []
    chunks = re.split(r"^##\s+\[.*?\]\s+.*$\n", content, flags=re.MULTILINE)
    for chunk in chunks[1:]:
        block = chunk.strip()
        if block:
            normalized = re.sub(r"\n{2,}", "\n", block)
            entries.append(normalized)
    return entries


# ── Heartbeat.md ──────────────────────────────────────────────────────────────

def read_heartbeat(session_id: str) -> str:
    p = _user_dir(session_id) / "heartbeat.md"
    return p.read_text() if p.exists() else "# Heartbeat Schedule\n\nNo automations configured yet."


def write_heartbeat(session_id: str, content: str) -> None:
    (_user_dir(session_id) / "heartbeat.md").write_text(content)


# ── Automations.json ──────────────────────────────────────────────────────────

def load_automations(session_id: str) -> list[dict[str, Any]]:
    p = _user_dir(session_id) / "automations.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        logger.warning("Malformed automations.json for session %s", session_id)
        return []


def save_automations(session_id: str, automations: list[dict[str, Any]]) -> None:
    (_user_dir(session_id) / "automations.json").write_text(json.dumps(automations, indent=2))


def add_automation(session_id: str, task: str, schedule: str, label: str = "") -> dict[str, Any]:
    """Add a new recurring automation. schedule can be cron expr or natural language."""
    automations = load_automations(session_id)
    automation: dict[str, Any] = {
        "id": f"auto_{len(automations) + 1}",
        "task": task,
        "schedule": schedule,
        "label": label or task[:60],
        "enabled": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run": None,
        "next_run": None,
    }
    automations.append(automation)
    save_automations(session_id, automations)
    hb = read_heartbeat(session_id)
    hb = hb.rstrip() + (
        f"\n\n### {automation['label']}\n"
        f"- Schedule: `{schedule}`\n"
        f"- Task: {task}\n"
        f"- ID: `{automation['id']}`\n"
    )
    write_heartbeat(session_id, hb)
    return automation


def list_automations_for_session(session_id: str) -> list[dict[str, Any]]:
    return load_automations(session_id)


def remove_automation(session_id: str, automation_id: str) -> bool:
    automations = load_automations(session_id)
    new_list = [a for a in automations if a["id"] != automation_id]
    if len(new_list) == len(automations):
        return False
    save_automations(session_id, new_list)
    return True


def list_all_sessions_with_automations() -> list[str]:
    """Return session IDs that have at least one automation file."""
    if not USER_DATA_ROOT.exists():
        return []
    return [d.name for d in USER_DATA_ROOT.iterdir() if d.is_dir() and (d / "automations.json").exists()]
