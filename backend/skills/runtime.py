"""Runtime skill resolution for websocket session settings."""

from __future__ import annotations

import logging
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select

from backend.database import RuntimeSkillInstallation, Skill, SkillToggle, SkillVersion, get_session

logger = logging.getLogger(__name__)

_RUNTIME_ALLOWED_STATUSES = {"published_global", "published_hub"}


@dataclass
class RuntimeSkillContext:
    """Server-authoritative set of runtime-enabled skills for a user session."""

    resolved_skill_ids: list[str] = field(default_factory=list)
    version_hashes: dict[str, str] = field(default_factory=dict)
    policy_refs: dict[str, str] = field(default_factory=dict)
    skill_allow_tools: list[str] | None = None
    skill_deny_tools: list[str] = field(default_factory=list)
    requested_skill_ids: list[str] = field(default_factory=list)
    resolved_at: datetime | None = None

    def as_settings_fragment(self) -> dict[str, Any]:
        """Return a cache-safe settings fragment persisted in runtime.settings."""
        fragment = {
            "resolved_skill_ids": list(self.resolved_skill_ids),
            "skill_runtime_meta": {
                "version_hashes": dict(self.version_hashes),
                "policy_refs": dict(self.policy_refs),
                "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            },
        }
        if self.skill_allow_tools is not None:
            fragment["skill_allow_tools"] = list(self.skill_allow_tools)
        if self.skill_deny_tools:
            fragment["skill_deny_tools"] = list(self.skill_deny_tools)
        return fragment


def _normalize_tool_names(raw_values: Any) -> set[str]:
    if not isinstance(raw_values, list):
        return set()
    normalized: set[str] = set()
    for raw in raw_values:
        if not isinstance(raw, str):
            continue
        tool = raw.strip().lower()
        if tool:
            normalized.add(tool)
    return normalized


def _extract_policy(metadata_json: str) -> tuple[set[str], set[str]]:
    try:
        metadata = json.loads(metadata_json or "{}")
    except json.JSONDecodeError:
        return set(), set()
    if not isinstance(metadata, dict):
        return set(), set()
    allow = _normalize_tool_names(metadata.get("skill_allow_tools"))
    deny = _normalize_tool_names(metadata.get("skill_deny_tools"))
    return allow, deny


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

    latest_version_by_skill = (
        select(SkillVersion.skill_id.label("skill_id"), func.max(SkillVersion.version).label("max_version"))
        .group_by(SkillVersion.skill_id)
        .subquery()
    )

    rows = await session.execute(
        select(Skill.id, Skill.status, SkillVersion.content_sha256, SkillVersion.metadata_json)
        .join(
            RuntimeSkillInstallation,
            and_(RuntimeSkillInstallation.skill_id == Skill.id, RuntimeSkillInstallation.user_id == user_uid),
        )
        .outerjoin(
            SkillToggle,
            and_(SkillToggle.skill_id == Skill.id, SkillToggle.user_id == user_uid),
        )
        .outerjoin(latest_version_by_skill, latest_version_by_skill.c.skill_id == Skill.id)
        .outerjoin(
            SkillVersion,
            and_(
                SkillVersion.skill_id == Skill.id,
                SkillVersion.version == latest_version_by_skill.c.max_version,
            ),
        )
        .where(Skill.id.in_(requested_ids))
        .where(or_(SkillToggle.enabled.is_(True), SkillToggle.id.is_(None)))
    )

    db_rows = rows.all()
    allowed: dict[str, str] = {}
    statuses_by_id: dict[str, str] = {}
    policy_by_id: dict[str, tuple[set[str], set[str]]] = {}
    for skill_id, status, content_sha256, metadata_json in db_rows:
        if status not in _RUNTIME_ALLOWED_STATUSES:
            continue
        skill_key = str(skill_id)
        allowed[skill_key] = str(content_sha256 or "")
        statuses_by_id[skill_key] = str(status)
        policy_by_id[skill_key] = _extract_policy(str(metadata_json or "{}"))

    resolved_ids = [skill_id for skill_id in requested_ids if skill_id in allowed]
    effective_allow: set[str] | None = None
    effective_deny: set[str] = set()
    for skill_id in resolved_ids:
        allow_tools, deny_tools = policy_by_id.get(skill_id, (set(), set()))
        effective_deny.update(deny_tools)
        if allow_tools:
            if effective_allow is None:
                effective_allow = set(allow_tools)
            else:
                effective_allow.intersection_update(allow_tools)
    if effective_allow is not None:
        effective_allow.difference_update(effective_deny)

    return RuntimeSkillContext(
        requested_skill_ids=requested_ids,
        resolved_skill_ids=resolved_ids,
        version_hashes={skill_id: allowed.get(skill_id, "") for skill_id in resolved_ids},
        policy_refs={skill_id: f"skill_status:{statuses_by_id.get(skill_id, 'unknown')}" for skill_id in resolved_ids},
        skill_allow_tools=sorted(effective_allow) if effective_allow is not None else None,
        skill_deny_tools=sorted(effective_deny),
        resolved_at=datetime.now(timezone.utc),
    )
