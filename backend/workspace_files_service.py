"""Global workspace-file templates used for every runtime session."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import PlatformSetting
from backend.session_workspace import get_session_files_root

logger = logging.getLogger(__name__)

WORKSPACE_FILE_NAMES: tuple[str, ...] = (
    "AGENTS.md",
    "BOOTSTRAP.md",
    "IDENTITY.md",
    "SOUL.md",
    "HEARTBEAT.md",
    "TOOLS.md",
    "USER.md",
)

WORKSPACE_FILE_KEY_PREFIX = "aegis_workspace_file:"

WORKSPACE_FILE_CANONICAL_NAME_MAP: dict[str, str] = {name.upper(): name for name in WORKSPACE_FILE_NAMES}

DEFAULT_WORKSPACE_FILE_CONTENTS: dict[str, str] = {
    "AGENTS.md": """# AGENTS.md - Your Workspace\n\nThis folder is home. Treat it that way.\n\n## Workspace Core Files\n- `BOOTSTRAP.md`\n- `IDENTITY.md`\n- `SOUL.md`\n- `HEARTBEAT.md`\n- `TOOLS.md`\n- `USER.md`\n\nThese files are global platform workspace files configured by admins and mounted into every Aegis runtime workspace.\n\n## Session Loop\n1. Read `SOUL.md`\n2. Read `USER.md`\n3. Read `HEARTBEAT.md`\n4. Apply `TOOLS.md` permissions and constraints\n""",
    "BOOTSTRAP.md": """# BOOTSTRAP.md\n\nYou just woke up.\n\n1. Load `IDENTITY.md` to understand your role.\n2. Load `SOUL.md` for behavior and tone.\n3. Load `USER.md` to align with who you are helping.\n4. Use `TOOLS.md` as the allowed-file operations contract.\n\nOnce complete, continue through normal task execution.\n""",
    "IDENTITY.md": """# IDENTITY.md\n\nYou are Aegis: an always-on AI coworker agent.\n\nYou operate from chat as the command center while using tools to execute work in the background.\n""",
    "SOUL.md": """# SOUL.md\n\nBe clear, grounded, and useful.\n\n- Acknowledge starts and ends explicitly.\n- Never fail silently.\n- Keep users oriented with concise progress updates.\n- Finish with outcomes and next steps.\n""",
    "HEARTBEAT.md": """# HEARTBEAT.md\n\nUse this file for recurring cadence reminders, standing checklists, and periodic responsibilities that keep sessions reliable.\n""",
    "TOOLS.md": """# TOOLS.md\n\nWorkspace file permissions for Aegis runtime:\n\n| File | Read | Write | Patch | Delete |\n|---|---|---|---|---|\n| `AGENTS.md` | ✅ | ✅ | ✅ | ✅ |\n| `BOOTSTRAP.md` | ✅ | ✅ | ✅ | ✅ |\n| `IDENTITY.md` | ✅ | ✅ | ✅ | ✅ |\n| `SOUL.md` | ✅ | ✅ | ✅ | ✅ |\n| `HEARTBEAT.md` | ✅ | ✅ | ✅ | ✅ |\n| `TOOLS.md` | ✅ | ✅ | ✅ | ✅ |\n| `USER.md` | ✅ | ✅ | ✅ | ✅ |\n\nThese permissions apply to workspace files provisioned into every user runtime workspace.\n""",
    "USER.md": """# USER.md\n\nDescribe the current user: goals, preferences, constraints, and success criteria.\n\nKeep this file concise and update it as understanding improves.\n""",
}


def _workspace_setting_key(file_name: str) -> str:
    canonical = WORKSPACE_FILE_CANONICAL_NAME_MAP.get(file_name.upper(), file_name)
    return f"{WORKSPACE_FILE_KEY_PREFIX}{canonical.upper()}"


async def list_workspace_files(db: AsyncSession) -> list[dict[str, str | None]]:
    """Return global workspace files in canonical display order."""
    items: list[dict[str, str | None]] = []
    for file_name in WORKSPACE_FILE_NAMES:
        row = await db.get(PlatformSetting, _workspace_setting_key(file_name))
        items.append(
            {
                "name": file_name,
                "content": row.value if row else DEFAULT_WORKSPACE_FILE_CONTENTS[file_name],
                "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
            }
        )
    return items


async def upsert_workspace_files(db: AsyncSession, files: Mapping[str, str], admin_uid: str) -> list[dict[str, str | None]]:
    """Persist one or more workspace markdown files as platform-global state."""
    for requested_name, content in files.items():
        normalized_name = requested_name.strip().upper()
        canonical_name = WORKSPACE_FILE_CANONICAL_NAME_MAP.get(normalized_name)
        if not canonical_name:
            continue
        key = _workspace_setting_key(canonical_name)
        row = await db.get(PlatformSetting, key)
        if row:
            row.value = str(content)
            row.updated_by = admin_uid
        else:
            db.add(PlatformSetting(key=key, value=str(content), updated_by=admin_uid))
    await db.flush()
    return await list_workspace_files(db)


async def materialize_workspace_files_for_session(db: AsyncSession, session_id: str) -> None:
    """Write current global workspace files into the active runtime session workspace."""
    files_root = get_session_files_root(session_id)
    files = await list_workspace_files(db)
    for item in files:
        name = str(item["name"])
        content = str(item["content"] or "")
        target = files_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


async def materialize_workspace_files_for_session_safe(db: AsyncSession, session_id: str) -> None:
    """Best-effort wrapper so runtime startup is never blocked by workspace sync errors."""
    try:
        await materialize_workspace_files_for_session(db, session_id)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to materialize workspace files for session %s", session_id)
