"""Workspace-file service with global defaults and per-user overrides."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from difflib import unified_diff

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import WorkspaceFileAuditEvent, WorkspaceFileGlobal, WorkspaceFileUser
from backend.session_workspace import get_session_files_root

logger = logging.getLogger(__name__)

WORKSPACE_FILE_NAMES: tuple[str, ...] = (
    "AGENTS.md",
    "BOOTSTRAP.md",
    "IDENTITY.md",
    "SOUL.md",
    "MEMORY.md",
    "TOOLS.md",
    "USER.md",
)

WORKSPACE_FILE_CANONICAL_NAME_MAP: dict[str, str] = {name.upper(): name for name in WORKSPACE_FILE_NAMES}

DEFAULT_WORKSPACE_FILE_CONTENTS: dict[str, str] = {
    "AGENTS.md": """# AGENTS.md - Your Workspace\n\nThis folder is home. Treat it that way.\n\n## Workspace Core Files\n- `BOOTSTRAP.md`\n- `IDENTITY.md`\n- `SOUL.md`\n- `MEMORY.md`\n- `TOOLS.md`\n- `USER.md`\n\nThese files are global platform workspace files configured by admins and mounted into every Aegis runtime workspace.\n\n## Session Loop\n1. Read `SOUL.md`\n2. Read `USER.md`\n3. Read `MEMORY.md`\n4. Apply `TOOLS.md` permissions and constraints\n""",
    "BOOTSTRAP.md": """# BOOTSTRAP.md\n\nYou just woke up.\n\n1. Load `IDENTITY.md` to understand your role.\n2. Load `SOUL.md` for behavior and tone.\n3. Load `USER.md` to align with who you are helping.\n4. Use `TOOLS.md` as the allowed-file operations contract.\n\nOnce complete, continue through normal task execution.\n""",
    "IDENTITY.md": """# IDENTITY.md\n\nYou are Aegis: an always-on AI coworker agent.\n\nYou operate from chat as the command center while using tools to execute work in the background.\n""",
    "SOUL.md": """# SOUL.md\n\nBe clear, grounded, and useful.\n\n- Acknowledge starts and ends explicitly.\n- Never fail silently.\n- Keep users oriented with concise progress updates.\n- Finish with outcomes and next steps.\n""",
    "MEMORY.md": """# MEMORY.md\n\nUse this file for durable user-specific context snapshots that should carry across runs.\n""",
    "TOOLS.md": """# TOOLS.md\n\nWorkspace file permissions for Aegis runtime:\n\n| File | Read | Write | Patch | Delete |\n|---|---|---|---|---|\n| `AGENTS.md` | ✅ | ✅ | ✅ | ✅ |\n| `BOOTSTRAP.md` | ✅ | ✅ | ✅ | ✅ |\n| `IDENTITY.md` | ✅ | ✅ | ✅ | ✅ |\n| `SOUL.md` | ✅ | ✅ | ✅ | ✅ |\n| `MEMORY.md` | ✅ | ✅ | ✅ | ✅ |\n| `TOOLS.md` | ✅ | ✅ | ✅ | ✅ |\n| `USER.md` | ✅ | ✅ | ✅ | ✅ |\n\nThese permissions apply to workspace files provisioned into every user runtime workspace.\n""",
    "USER.md": """# USER.md\n\nDescribe the current user: goals, preferences, constraints, and success criteria.\n\nKeep this file concise and update it as understanding improves.\n""",
}


def normalize_workspace_file_name(file_name: str) -> str | None:
    """Return canonical file name when supported, otherwise ``None``."""
    return WORKSPACE_FILE_CANONICAL_NAME_MAP.get(file_name.strip().upper())


def _diff_hash(old_content: str, new_content: str) -> str:
    diff_text = "\n".join(
        unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )
    return hashlib.sha256(diff_text.encode("utf-8")).hexdigest()


async def _log_workspace_audit(
    db: AsyncSession,
    *,
    actor_id: str,
    scope: str,
    operation: str,
    file_name: str,
    old_content: str,
    new_content: str,
) -> None:
    db.add(
        WorkspaceFileAuditEvent(
            actor_id=actor_id,
            scope=scope,
            operation=operation,
            file_name=file_name,
            diff_hash=_diff_hash(old_content, new_content),
        )
    )
    await db.flush()


async def list_global_workspace_files(db: AsyncSession) -> list[dict[str, str | None]]:
    """Return admin-managed global defaults in canonical order."""
    rows = {
        row.name: row
        for row in (
            await db.execute(select(WorkspaceFileGlobal).where(WorkspaceFileGlobal.name.in_(WORKSPACE_FILE_NAMES)))
        ).scalars()
    }
    items: list[dict[str, str | None]] = []
    for file_name in WORKSPACE_FILE_NAMES:
        row = rows.get(file_name)
        items.append(
            {
                "name": file_name,
                "content": row.content if row else DEFAULT_WORKSPACE_FILE_CONTENTS[file_name],
                "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
            }
        )
    return items


async def list_user_workspace_files(db: AsyncSession, user_id: str) -> list[dict[str, str | None | bool]]:
    """Return effective file view for a user with override provenance."""
    global_files = await list_global_workspace_files(db)
    user_rows = {
        row.name: row
        for row in (
            await db.execute(
                select(WorkspaceFileUser).where(
                    WorkspaceFileUser.user_id == user_id,
                    WorkspaceFileUser.name.in_(WORKSPACE_FILE_NAMES),
                )
            )
        ).scalars()
    }
    items: list[dict[str, str | None | bool]] = []
    for global_item in global_files:
        name = str(global_item["name"])
        override = user_rows.get(name)
        items.append(
            {
                "name": name,
                "content": override.content if override else global_item["content"],
                "updated_at": (
                    override.updated_at.isoformat()
                    if override and override.updated_at
                    else global_item["updated_at"]
                ),
                "has_override": bool(override),
                "source": "user" if override else "global",
            }
        )
    return items


async def upsert_global_workspace_file(
    db: AsyncSession,
    *,
    file_name: str,
    content: str,
    actor_id: str,
    operation: str,
) -> dict[str, str | None]:
    """Create/update a global workspace file with audit logging."""
    canonical_name = normalize_workspace_file_name(file_name)
    if not canonical_name:
        raise ValueError(f"Unsupported workspace file: {file_name}")
    row = await db.get(WorkspaceFileGlobal, canonical_name)
    old_content = (row.content if row else DEFAULT_WORKSPACE_FILE_CONTENTS[canonical_name]) or ""
    if row:
        row.content = content
        row.updated_by = actor_id
    else:
        db.add(WorkspaceFileGlobal(name=canonical_name, content=content, updated_by=actor_id))
    await _log_workspace_audit(
        db,
        actor_id=actor_id,
        scope="global",
        operation=operation,
        file_name=canonical_name,
        old_content=old_content,
        new_content=content,
    )
    await db.flush()
    return await get_global_workspace_file(db, canonical_name)


async def upsert_user_workspace_file(
    db: AsyncSession,
    *,
    user_id: str,
    file_name: str,
    content: str,
    actor_id: str,
    operation: str,
) -> dict[str, str | None | bool]:
    """Create/update a user-local override with audit logging."""
    canonical_name = normalize_workspace_file_name(file_name)
    if not canonical_name:
        raise ValueError(f"Unsupported workspace file: {file_name}")
    existing_override = await db.scalar(
        select(WorkspaceFileUser).where(WorkspaceFileUser.user_id == user_id, WorkspaceFileUser.name == canonical_name)
    )
    global_row = await db.get(WorkspaceFileGlobal, canonical_name)
    old_content = (
        existing_override.content
        if existing_override
        else (global_row.content if global_row else DEFAULT_WORKSPACE_FILE_CONTENTS[canonical_name])
    ) or ""
    if existing_override:
        existing_override.content = content
        existing_override.updated_by = actor_id
    else:
        db.add(
            WorkspaceFileUser(
                user_id=user_id,
                name=canonical_name,
                content=content,
                updated_by=actor_id,
            )
        )
    await _log_workspace_audit(
        db,
        actor_id=actor_id,
        scope="user",
        operation=operation,
        file_name=canonical_name,
        old_content=old_content,
        new_content=content,
    )
    await db.flush()
    return await get_effective_workspace_file(db, user_id, canonical_name)


async def delete_user_workspace_file_override(
    db: AsyncSession,
    *,
    user_id: str,
    file_name: str,
    actor_id: str,
) -> None:
    """Delete local override to revert to global value and record audit event."""
    canonical_name = normalize_workspace_file_name(file_name)
    if not canonical_name:
        raise ValueError(f"Unsupported workspace file: {file_name}")
    override = await db.scalar(
        select(WorkspaceFileUser).where(WorkspaceFileUser.user_id == user_id, WorkspaceFileUser.name == canonical_name)
    )
    if not override:
        return
    global_row = await db.get(WorkspaceFileGlobal, canonical_name)
    reverted_content = (global_row.content if global_row else DEFAULT_WORKSPACE_FILE_CONTENTS[canonical_name]) or ""
    old_content = override.content or ""
    await db.delete(override)
    await _log_workspace_audit(
        db,
        actor_id=actor_id,
        scope="user",
        operation="delete",
        file_name=canonical_name,
        old_content=old_content,
        new_content=reverted_content,
    )
    await db.flush()


async def get_global_workspace_file(db: AsyncSession, file_name: str) -> dict[str, str | None]:
    """Return current global file payload."""
    canonical_name = normalize_workspace_file_name(file_name)
    if not canonical_name:
        raise ValueError(f"Unsupported workspace file: {file_name}")
    row = await db.get(WorkspaceFileGlobal, canonical_name)
    return {
        "name": canonical_name,
        "content": row.content if row else DEFAULT_WORKSPACE_FILE_CONTENTS[canonical_name],
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


async def get_effective_workspace_file(
    db: AsyncSession,
    user_id: str,
    file_name: str,
) -> dict[str, str | None | bool]:
    """Resolve effective file: local override if present, otherwise global default."""
    canonical_name = normalize_workspace_file_name(file_name)
    if not canonical_name:
        raise ValueError(f"Unsupported workspace file: {file_name}")
    override = await db.scalar(
        select(WorkspaceFileUser).where(WorkspaceFileUser.user_id == user_id, WorkspaceFileUser.name == canonical_name)
    )
    if override:
        return {
            "name": canonical_name,
            "content": override.content,
            "updated_at": override.updated_at.isoformat() if override.updated_at else None,
            "has_override": True,
            "source": "user",
        }
    global_file = await get_global_workspace_file(db, canonical_name)
    return {
        "name": canonical_name,
        "content": global_file["content"],
        "updated_at": global_file["updated_at"],
        "has_override": False,
        "source": "global",
    }


async def upsert_workspace_files(db: AsyncSession, files: Mapping[str, str], admin_uid: str) -> list[dict[str, str | None]]:
    """Legacy admin bulk upsert helper used by existing admin endpoint."""
    invalid_names: list[str] = []
    for requested_name, content in files.items():
        canonical = normalize_workspace_file_name(requested_name)
        if not canonical:
            invalid_names.append(requested_name)
            continue
        await upsert_global_workspace_file(
            db,
            file_name=canonical,
            content=str(content),
            actor_id=admin_uid,
            operation="patch",
        )
    if invalid_names:
        logger.warning("Unsupported workspace file names were rejected: %s", ", ".join(sorted(invalid_names)))
        raise ValueError(f"Unsupported workspace files: {', '.join(sorted(invalid_names))}")
    await db.flush()
    return await list_global_workspace_files(db)


async def list_workspace_files(db: AsyncSession) -> list[dict[str, str | None]]:
    """Backward-compatible alias for legacy consumers."""
    return await list_global_workspace_files(db)


async def materialize_workspace_files_for_session(db: AsyncSession, session_id: str, user_id: str | None) -> None:
    """Write effective workspace files into the active runtime session workspace."""
    files_root = get_session_files_root(session_id)
    if user_id:
        files = await list_user_workspace_files(db, user_id=user_id)
    else:
        files = await list_global_workspace_files(db)
    for item in files:
        name = str(item["name"])
        content = str(item["content"] or "")
        target = files_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


async def materialize_workspace_files_for_session_safe(db: AsyncSession, session_id: str, user_id: str | None) -> None:
    """Best-effort wrapper so runtime startup is never blocked by workspace sync errors."""
    try:
        await materialize_workspace_files_for_session(db, session_id, user_id)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to materialize workspace files for session %s", session_id)
