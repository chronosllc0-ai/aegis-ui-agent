"""Runtime skill resolution for websocket session settings."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, select

from backend.database import Skill, SkillInstallation, SkillToggle, SkillVersion, get_session

logger = logging.getLogger(__name__)

_RUNTIME_ALLOWED_STATUSES = {"published_global", "published_hub"}


@dataclass
class RuntimeSkillContext:
    """Server-authoritative set of runtime-enabled skills for a user session."""

    resolved_skill_ids: list[str] = field(default_factory=list)
    version_hashes: dict[str, str] = field(default_factory=dict)
    policy_refs: dict[str, str] = field(default_factory=dict)
    requested_skill_ids: list[str] = field(default_factory=list)
    resolved_at: datetime | None = None

    def as_settings_fragment(self) -> dict[str, Any]:
        """Return a cache-safe settings fragment persisted in runtime.settings."""
        return {
            "resolved_skill_ids": list(self.resolved_skill_ids),
            "skill_runtime_meta": {
                "version_hashes": dict(self.version_hashes),
                "policy_refs": dict(self.policy_refs),
                "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            },
        }


async def resolve_runtime_skills(user_uid: str | None, requested_ids: list[str]) -> RuntimeSkillContext:
    """Resolve requested skill IDs into installed+enabled+runtime-allowed skill IDs.

    Gracefully degrades to an empty context when authentication is missing or the DB is unavailable.
    """
    deduped_requested = [sid for sid in dict.fromkeys(str(raw).strip() for raw in requested_ids) if sid]
    if not user_uid:
        return RuntimeSkillContext(requested_skill_ids=deduped_requested, resolved_at=datetime.now(timezone.utc))

    try:
        async for session in get_session():
            context = await _resolve_with_session(session=session, user_uid=user_uid, requested_ids=deduped_requested)
            return context
    except (HTTPException, RuntimeError) as exc:
        logger.warning("Runtime skill resolution unavailable for user %s: %s", user_uid, exc)
    except Exception:
        logger.exception("Runtime skill resolution failed for user %s", user_uid)

    return RuntimeSkillContext(requested_skill_ids=deduped_requested, resolved_at=datetime.now(timezone.utc))


async def _resolve_with_session(*, session, user_uid: str, requested_ids: list[str]) -> RuntimeSkillContext:
    if not requested_ids:
        return RuntimeSkillContext(requested_skill_ids=[], resolved_at=datetime.now(timezone.utc))

    rows = await session.execute(
        select(Skill.id, Skill.status, SkillVersion.content_sha256)
        .join(SkillInstallation, and_(SkillInstallation.skill_id == Skill.id, SkillInstallation.user_id == user_uid))
        .join(SkillToggle, and_(SkillToggle.skill_id == Skill.id, SkillToggle.user_id == user_uid, SkillToggle.enabled.is_(True)))
        .outerjoin(SkillVersion, SkillVersion.skill_id == Skill.id)
        .where(Skill.id.in_(requested_ids))
    )

    db_rows = rows.all()
    allowed: dict[str, str] = {}
    statuses_by_id: dict[str, str] = {}
    for skill_id, status, content_sha256 in db_rows:
        if status not in _RUNTIME_ALLOWED_STATUSES:
            continue
        skill_key = str(skill_id)
        allowed[skill_key] = str(content_sha256 or "")
        statuses_by_id[skill_key] = str(status)

    resolved_ids = [skill_id for skill_id in requested_ids if skill_id in allowed]
    return RuntimeSkillContext(
        requested_skill_ids=requested_ids,
        resolved_skill_ids=resolved_ids,
        version_hashes={skill_id: allowed.get(skill_id, "") for skill_id in resolved_ids},
        policy_refs={skill_id: f"skill_status:{statuses_by_id.get(skill_id, 'unknown')}" for skill_id in resolved_ids},
        resolved_at=datetime.now(timezone.utc),
    )
