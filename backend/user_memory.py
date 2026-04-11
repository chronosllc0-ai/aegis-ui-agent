"""Per-user persistent memory and automation storage for Aegis.

Files:
  /data/users/{session_id}/memory.md     — User preferences, facts, context
  /data/users/{session_id}/heartbeat.md  — Human-readable automation schedule
  /data/users/{session_id}/automations.json — Structured automation configs
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

USER_DATA_ROOT = Path(os.environ.get("USER_DATA_ROOT", "/data/users"))


def _user_dir(session_id: str) -> Path:
    d = USER_DATA_ROOT / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Memory.md ─────────────────────────────────────────────────────────

def read_memory(session_id: str) -> str:
    p = _user_dir(session_id) / "memory.md"
    return p.read_text() if p.exists() else "# Memory\n\nNo memory stored yet."


def write_memory(session_id: str, content: str) -> None:
    (_user_dir(session_id) / "memory.md").write_text(content)


def patch_memory(session_id: str, section: str, content: str) -> str:
    """Update or append a named section in memory.md. Returns new full content."""
    current = read_memory(session_id)
    header = f"## {section}"
    if header in current:
        # Replace the section content up to the next ## heading or EOF
        pattern = rf"(## {re.escape(section)}\n)(.*?)(?=\n## |\Z)"
        replacement = rf"\g<1>{content}\n"
        updated = re.sub(pattern, replacement, current, flags=re.DOTALL)
    else:
        updated = current.rstrip() + f"\n\n## {section}\n{content}\n"
    write_memory(session_id, updated)
    return updated


# ── Heartbeat.md ──────────────────────────────────────────────────────

def read_heartbeat(session_id: str) -> str:
    p = _user_dir(session_id) / "heartbeat.md"
    return p.read_text() if p.exists() else "# Heartbeat Schedule\n\nNo automations configured yet."


def write_heartbeat(session_id: str, content: str) -> None:
    (_user_dir(session_id) / "heartbeat.md").write_text(content)


# ── Automations.json ──────────────────────────────────────────────────

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
    p = _user_dir(session_id) / "automations.json"
    p.write_text(json.dumps(automations, indent=2))


def add_automation(session_id: str, task: str, schedule: str, label: str = "") -> dict[str, Any]:
    """Add a new automation. schedule can be cron expr or natural language."""
    automations = load_automations(session_id)
    automation = {
        "id": f"auto_{len(automations)+1}",
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
    # Also update heartbeat.md
    hb = read_heartbeat(session_id)
    hb = hb.rstrip() + f"\n\n### {automation['label']}\n- Schedule: `{schedule}`\n- Task: {task}\n- ID: `{automation['id']}`\n"
    write_heartbeat(session_id, hb)
    return automation


def remove_automation(session_id: str, automation_id: str) -> bool:
    automations = load_automations(session_id)
    new_list = [a for a in automations if a["id"] != automation_id]
    if len(new_list) == len(automations):
        return False
    save_automations(session_id, new_list)
    return True


def list_automations(session_id: str) -> list[dict[str, Any]]:
    """Return all automations for a session."""
    return load_automations(session_id)


def list_all_sessions_with_automations() -> list[str]:
    """Return session IDs that have at least one enabled automation."""
    if not USER_DATA_ROOT.exists():
        return []
    result = []
    for d in USER_DATA_ROOT.iterdir():
        if d.is_dir() and (d / "automations.json").exists():
            result.append(d.name)
    return result
