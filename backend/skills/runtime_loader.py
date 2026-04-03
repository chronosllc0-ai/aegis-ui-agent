"""Runtime skill loader for approved, reviewed, and scan-resolved skill directives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Literal

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Skill, SkillReview, SkillScanResult, SkillVersion
from config import settings

logger = logging.getLogger(__name__)

APPROVED_STATUSES = {"approved_internal", "approved_marketplace"}
_APPROVED_REVIEW_DECISIONS = {"approve_internal", "approve_marketplace"}


@dataclass
class RuntimeSkill:
    """Skill payload prepared for runtime prompt injection."""

    skill_id: str
    version_id: str
    name: str
    source: Literal["global", "hub", "user"]
    priority: int
    content: str


async def get_active_runtime_skills(session: AsyncSession, user_id: str, session_id: str) -> list[RuntimeSkill]:
    """Return approved and security-cleared runtime skills for this user/session."""
    rows = await session.execute(
        select(Skill)
        .where(Skill.status.in_(APPROVED_STATUSES))
        .order_by(desc(Skill.updated_at), desc(Skill.created_at))
    )

    active: list[RuntimeSkill] = []

    for skill in rows.scalars().all():
        version = await _latest_version(session, skill.id)
        if version is None:
            logger.warning("Runtime skill %s excluded: missing_latest_version", skill.id)
            continue

        metadata = _parse_metadata(version.metadata_json)
        if metadata is None:
            logger.warning("Runtime skill %s excluded: malformed_metadata", skill.id)
            continue

        if _is_disabled(metadata, user_id=user_id, session_id=session_id):
            continue

        if not await _is_security_resolved(session, version.id):
            logger.warning("Runtime skill %s excluded: unresolved_scan_or_review", skill.id)
            continue

        active.append(
            RuntimeSkill(
                skill_id=skill.id,
                version_id=version.id,
                name=skill.name,
                source=_resolve_source(skill.visibility, owner_user_id=skill.owner_user_id, user_id=user_id),
                priority=_extract_priority(metadata),
                content=str(metadata.get("skill_md") or "").strip(),
            )
        )

    return active


async def _latest_version(session: AsyncSession, skill_id: str) -> SkillVersion | None:
    row = await session.execute(
        select(SkillVersion)
        .where(SkillVersion.skill_id == skill_id)
        .order_by(desc(SkillVersion.version), desc(SkillVersion.created_at))
        .limit(1)
    )
    return row.scalar_one_or_none()


def _parse_metadata(raw: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _extract_priority(metadata: dict[str, object]) -> int:
    value = metadata.get("priority", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _is_disabled(metadata: dict[str, object], *, user_id: str, session_id: str) -> bool:
    disabled_for_users = _coerce_string_set(metadata.get("disabled_for_user_ids"))
    if user_id in disabled_for_users:
        return True

    disabled_for_sessions = _coerce_string_set(metadata.get("disabled_for_session_ids"))
    if session_id in disabled_for_sessions:
        return True

    return bool(metadata.get("disabled"))


def _coerce_string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    output: set[str] = set()
    for item in value:
        if isinstance(item, str) and item.strip():
            output.add(item.strip())
    return output


def _resolve_source(visibility: str, *, owner_user_id: str, user_id: str) -> Literal["global", "hub", "user"]:
    normalized = visibility.strip().lower()
    if normalized in {"global", "hub"}:
        return normalized
    if owner_user_id == user_id:
        return "user"
    return "hub"


async def _is_security_resolved(session: AsyncSession, skill_version_id: str) -> bool:
    review_row = await session.execute(
        select(SkillReview)
        .where(SkillReview.skill_version_id == skill_version_id)
        .order_by(desc(SkillReview.reviewed_at), desc(SkillReview.created_at))
        .limit(1)
    )
    review = review_row.scalar_one_or_none()
    if review is None or review.decision not in _APPROVED_REVIEW_DECISIONS:
        return False

    scan_rows = await session.execute(select(SkillScanResult).where(SkillScanResult.skill_version_id == skill_version_id))
    scans = {scan.engine: scan for scan in scan_rows.scalars().all()}

    policy = scans.get("policy")
    if policy is None or policy.verdict not in {"pass", "warn"}:
        return False

    vt = scans.get("virustotal")
    if settings.VIRUSTOTAL_REQUIRED:
        if vt is None or vt.verdict not in {"pass", "warn"}:
            return False
    else:
        if vt is not None and vt.verdict not in {"pass", "warn", "skipped"}:
            return False

    return True
