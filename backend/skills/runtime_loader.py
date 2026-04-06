"""Runtime skill loader for installed, enabled, approved, and scan-resolved skills."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import logging

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Skill, SkillInstall, SkillReview, SkillScanResult, SkillVersion
from config import settings

logger = logging.getLogger(__name__)

APPROVED_STATUSES = {"approved_global", "approved_hub"}
_APPROVED_REVIEW_DECISIONS = {"approve_global", "approve_hub"}


@dataclass
class RuntimeSkill:
    """Skill payload prepared for runtime prompt injection."""

    skill_id: str
    version_id: str
    name: str
    source: str
    content: str
    provenance: dict[str, str] = field(default_factory=dict)
    priority: int = 0
    created_at: datetime | None = None


async def get_active_runtime_skills(session: AsyncSession, user_id: str, session_id: str) -> list[RuntimeSkill]:
    """Return installed + enabled skills that passed all gates and budget checks."""
    _ = session_id
    rows = await session.execute(
        select(SkillInstall, Skill, SkillVersion)
        .join(Skill, Skill.id == SkillInstall.skill_id)
        .join(SkillVersion, SkillVersion.id == SkillInstall.skill_version_id)
        .where(and_(SkillInstall.user_id == user_id, SkillInstall.enabled.is_(True)))
        .order_by(desc(SkillInstall.updated_at))
    )
    install_rows = rows.all()

    runtime: list[RuntimeSkill] = []
    configured_budget = max(int(getattr(settings, "SKILLS_MAX_TOKEN", settings.SKILLS_MAX_TOKENS)), 1)
    hard_budget_cap = max(int(settings.SKILLS_MAX_TOKENS), 1)
    remaining_budget = min(configured_budget, hard_budget_cap)
    version_ids = [version.id for _, _, version in install_rows]

    scans_by_version_id: dict[str, dict[str, SkillScanResult]] = {}
    latest_review_by_version_id: dict[str, SkillReview] = {}
    if version_ids:
        scan_rows = await session.execute(
            select(SkillScanResult)
            .where(SkillScanResult.skill_version_id.in_(version_ids))
            .order_by(desc(SkillScanResult.scanned_at), desc(SkillScanResult.created_at))
        )
        for scan in scan_rows.scalars().all():
            by_engine = scans_by_version_id.setdefault(scan.skill_version_id, {})
            by_engine.setdefault(scan.engine, scan)

        review_rows = await session.execute(
            select(SkillReview)
            .where(SkillReview.skill_version_id.in_(version_ids))
            .order_by(desc(SkillReview.reviewed_at), desc(SkillReview.created_at))
        )
        for review in review_rows.scalars().all():
            latest_review_by_version_id.setdefault(review.skill_version_id, review)

    for install, skill, version in install_rows:
        if skill.status not in APPROVED_STATUSES:
            logger.warning("Runtime skill %s excluded: not_approved_status", skill.id)
            continue

        if not _is_security_resolved(
            review=latest_review_by_version_id.get(version.id),
            scans_by_engine=scans_by_version_id.get(version.id, {}),
        ):
            logger.warning("Runtime skill %s excluded: unresolved_scan_or_review", skill.id)
            continue

        metadata = _parse_metadata(version.metadata_json)
        if metadata is None:
            logger.warning("Runtime skill %s excluded: malformed_metadata", skill.id)
            continue

        content = str(metadata.get("skill_md") or "").strip()
        estimated_tokens = max(1, len(content) // 4)
        if estimated_tokens > remaining_budget:
            logger.warning("Runtime skill %s excluded: token_budget_exceeded", skill.id)
            continue

        remaining_budget -= estimated_tokens
        parsed_priority = _parse_priority(metadata.get("priority"))
        provenance = {
            "publish_target": skill.publish_target,
            "status": skill.status,
            "content_sha256": version.content_sha256,
            "installed_by": install.user_id,
        }
        runtime.append(
            RuntimeSkill(
                skill_id=skill.id,
                version_id=version.id,
                name=skill.name,
                source=skill.publish_target,
                content=content,
                provenance=provenance,
                priority=parsed_priority,
                created_at=version.created_at,
            )
        )

    return runtime


def _parse_metadata(raw: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_priority(raw: object) -> int:
    """Parse runtime skill priority from metadata with safe fallback."""
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw.strip())
        except ValueError:
            return 0
    return 0


def _is_security_resolved(*, review: SkillReview | None, scans_by_engine: dict[str, SkillScanResult]) -> bool:
    if review is None or review.decision not in _APPROVED_REVIEW_DECISIONS:
        return False

    policy = scans_by_engine.get("policy")
    if policy is None or policy.verdict not in {"pass", "warn"}:
        return False

    vt = scans_by_engine.get("virustotal")
    if settings.VIRUSTOTAL_REQUIRED:
        return vt is not None and vt.verdict in {"pass", "warn"}
    if vt is None:
        return False
    return vt.verdict in {"pass", "warn", "skipped"}
