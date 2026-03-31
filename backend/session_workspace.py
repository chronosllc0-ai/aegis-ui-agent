"""Ephemeral per-session workspace helpers.

All local file, code-execution, and GitHub repo-engineering work happens inside a
session-scoped directory rooted under ``/tmp``. The workspace is created lazily
and can be deleted when the websocket session disconnects.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
import re

SESSION_WORKSPACE_ROOT = Path("/tmp") / "aegis-session-workspaces"
_SESSION_ID_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_session_id(session_id: str) -> str:
    """Return a filesystem-safe session identifier."""
    cleaned = _SESSION_ID_RE.sub("-", session_id.strip())
    return cleaned or "anonymous-session"


def get_session_workspace_root(session_id: str) -> Path:
    """Return the root directory for a session workspace."""
    return SESSION_WORKSPACE_ROOT / _sanitize_session_id(session_id)


def ensure_session_workspace(session_id: str) -> Path:
    """Create and return the session workspace root."""
    root = get_session_workspace_root(session_id)
    (root / "files").mkdir(parents=True, exist_ok=True)
    (root / "repos").mkdir(parents=True, exist_ok=True)
    return root


def get_session_files_root(session_id: str) -> Path:
    """Return the default files directory for a session."""
    return ensure_session_workspace(session_id) / "files"


def get_session_repos_root(session_id: str) -> Path:
    """Return the cloned-repositories directory for a session."""
    return ensure_session_workspace(session_id) / "repos"


def resolve_session_path(session_id: str, requested_path: str | None) -> Path:
    """Resolve a path inside the session workspace and reject path traversal."""
    root = ensure_session_workspace(session_id).resolve(strict=False)
    files_root = (root / "files").resolve(strict=False)
    candidate = Path(requested_path or ".")
    if not candidate.is_absolute():
        candidate = files_root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("Path must stay inside the current Aegis session workspace.") from exc
    return resolved


async def cleanup_session_workspace(session_id: str) -> None:
    """Delete the session workspace tree if it exists.

    Uses ``asyncio.to_thread`` so the blocking ``shutil.rmtree`` call does not
    stall the event loop when invoked from an async websocket disconnect handler.
    """
    await asyncio.to_thread(shutil.rmtree, get_session_workspace_root(session_id), True)
