"""Persistence helpers for organization skill policy and admin allow/block controls."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import PlatformSetting

SKILLS_POLICY_KEY = "aegis_skills_policy_v1"
SKILLS_BLOCKLIST_KEY = "aegis_skills_blocklist_v1"

DEFAULT_SKILLS_POLICY: dict[str, Any] = {
    "allow_unreviewed_installs": False,
    "block_high_risk_skills": False,
    "require_approval_before_install": False,
    "default_enabled_skill_ids": [],
}


def _safe_load_json(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        loaded = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


async def _get_setting(db: AsyncSession, key: str) -> PlatformSetting | None:
    result = await db.execute(select(PlatformSetting).where(PlatformSetting.key == key))
    return result.scalar_one_or_none()


async def get_skills_policy(db: AsyncSession) -> dict[str, Any]:
    """Return merged and normalized org skills policy."""
    row = await _get_setting(db, SKILLS_POLICY_KEY)
    value = _safe_load_json(row.value if row else None)
    default_ids = value.get("default_enabled_skill_ids")
    return {
        "allow_unreviewed_installs": bool(value.get("allow_unreviewed_installs", DEFAULT_SKILLS_POLICY["allow_unreviewed_installs"])),
        "block_high_risk_skills": bool(value.get("block_high_risk_skills", DEFAULT_SKILLS_POLICY["block_high_risk_skills"])),
        "require_approval_before_install": bool(value.get("require_approval_before_install", DEFAULT_SKILLS_POLICY["require_approval_before_install"])),
        "default_enabled_skill_ids": [skill_id for skill_id in (default_ids or []) if isinstance(skill_id, str) and skill_id.strip()],
    }


async def set_skills_policy(db: AsyncSession, *, policy: dict[str, Any], admin_uid: str) -> dict[str, Any]:
    """Persist org skills policy and return normalized value."""
    normalized = {
        "allow_unreviewed_installs": bool(policy.get("allow_unreviewed_installs", False)),
        "block_high_risk_skills": bool(policy.get("block_high_risk_skills", False)),
        "require_approval_before_install": bool(policy.get("require_approval_before_install", False)),
        "default_enabled_skill_ids": [skill_id.strip() for skill_id in policy.get("default_enabled_skill_ids", []) if isinstance(skill_id, str) and skill_id.strip()],
    }
    row = await _get_setting(db, SKILLS_POLICY_KEY)
    serialized = json.dumps(normalized)
    if row is None:
        db.add(PlatformSetting(key=SKILLS_POLICY_KEY, value=serialized, updated_by=admin_uid))
    else:
        row.value = serialized
        row.updated_by = admin_uid
    await db.flush()
    return normalized


async def get_blocklist_state(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Return skill allow/block state map keyed by skill id."""
    row = await _get_setting(db, SKILLS_BLOCKLIST_KEY)
    raw = _safe_load_json(row.value if row else None)
    normalized: dict[str, dict[str, Any]] = {}
    for skill_id, entry in raw.items():
        if not isinstance(skill_id, str) or not isinstance(entry, dict):
            continue
        state = str(entry.get("state", ""))
        if state not in {"allow", "block"}:
            continue
        normalized[skill_id] = {
            "state": state,
            "updated_at": entry.get("updated_at"),
            "updated_by": entry.get("updated_by"),
        }
    return normalized


async def set_blocklist_state(db: AsyncSession, *, state: dict[str, dict[str, Any]], admin_uid: str) -> None:
    """Persist full blocklist state map."""
    row = await _get_setting(db, SKILLS_BLOCKLIST_KEY)
    serialized = json.dumps(state)
    if row is None:
        db.add(PlatformSetting(key=SKILLS_BLOCKLIST_KEY, value=serialized, updated_by=admin_uid))
    else:
        row.value = serialized
        row.updated_by = admin_uid
    await db.flush()
