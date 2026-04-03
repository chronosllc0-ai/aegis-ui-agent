"""Business logic for versioned, scanned, and reviewed skills."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import (
    Skill,
    SkillPublishEvent,
    SkillReview,
    SkillScanResult,
    SkillVersion,
    User,
)
from config import settings

logger = logging.getLogger(__name__)


class VirusTotalScanner:
    """Thin VT client with timeout/retry and a simple circuit breaker."""

    _consecutive_failures = 0
    _opened_until: datetime | None = None
    _lock = asyncio.Lock()

    @classmethod
    @classmethod
    def _is_open(cls) -> bool:
        if cls._opened_until is None:
            return False
        return datetime.now(timezone.utc) < cls._opened_until  # NOTE: not lock-guarded; safe only in single-worker
        if cls._opened_until is None:
            return False
        return datetime.now(timezone.utc) < cls._opened_until

    @classmethod
    async def _register_failure(cls) -> None:
        """Increment breaker failure count and open circuit when threshold is exceeded."""
        async with cls._lock:
            cls._consecutive_failures += 1
            if cls._consecutive_failures >= 3:
                cls._opened_until = datetime.now(timezone.utc) + timedelta(minutes=5)

    @classmethod
    async def _register_success(cls) -> None:
        """Reset breaker state after a successful VT interaction."""
        async with cls._lock:
            cls._consecutive_failures = 0
            cls._opened_until = None

    @classmethod
    async def scan_content(cls, *, file_name: str, content: bytes) -> dict[str, Any]:
        """Run VirusTotal hash lookup/upload flow and return a normalized payload."""
        if not settings.VIRUSTOTAL_API_KEY:
            return {
                "engine": "virustotal",
                "verdict": "skipped",
                "score": 0.0,
                "raw_json": {"reason": "missing_api_key"},
                "report_url": None,
                "scanned_at": datetime.now(timezone.utc),
            }

        if len(content) > settings.VIRUSTOTAL_MAX_FILE_BYTES:
            return {
                "engine": "virustotal",
                "verdict": "error",
                "score": 1.0,
                "raw_json": {"reason": "file_too_large", "max_bytes": settings.VIRUSTOTAL_MAX_FILE_BYTES},
                "report_url": None,
                "scanned_at": datetime.now(timezone.utc),
            }

        if cls._is_open():
            return {
                "engine": "virustotal",
                "verdict": "error",
                "score": 1.0,
                "raw_json": {"reason": "circuit_open"},
                "report_url": None,
                "scanned_at": datetime.now(timezone.utc),
            }

        sha256 = hashlib.sha256(content).hexdigest()
        headers = {"x-apikey": settings.VIRUSTOTAL_API_KEY}
        timeout = httpx.Timeout(settings.VIRUSTOTAL_TIMEOUT_SECONDS)

        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
                file_report = await client.get(f"https://www.virustotal.com/api/v3/files/{sha256}")
                if file_report.status_code == 404:
                    upload_response = await client.post(
                        "https://www.virustotal.com/api/v3/files",
                        files={"file": (file_name, content, "text/markdown")},
                    )
                    upload_response.raise_for_status()
                    analysis_id = upload_response.json().get("data", {}).get("id")
                    final_status = "queued"
                    if analysis_id:
                        for _ in range(settings.VIRUSTOTAL_MAX_POLLS):
                            poll_response = await client.get(
                                f"https://www.virustotal.com/api/v3/analyses/{analysis_id}"
                            )
                            poll_response.raise_for_status()
                            poll_json = poll_response.json()
                            final_status = poll_json.get("data", {}).get("attributes", {}).get("status", "queued")
                            if final_status == "completed":
                                break
                            await asyncio.sleep(settings.VIRUSTOTAL_POLL_INTERVAL_SECONDS)
                    if final_status != "completed":
                        return {
                            "engine": "virustotal",
                            "verdict": "error",
                            "score": 1.0,
                            "raw_json": {
                                "reason": "analysis_timeout",
                                "max_polls": settings.VIRUSTOTAL_MAX_POLLS,
                                "last_status": final_status,
                            },
                            "report_url": None,
                            "scanned_at": datetime.now(timezone.utc),
                        }
                    file_report = await client.get(f"https://www.virustotal.com/api/v3/files/{sha256}")
                file_report.raise_for_status()
                raw = file_report.json()
        except (httpx.RequestError, httpx.HTTPStatusError, OSError) as exc:
            await cls._register_failure()
            logger.warning("VirusTotal scan failed: %s", exc)
            return {
                "engine": "virustotal",
                "verdict": "error",
                "score": 1.0,
                "raw_json": {"reason": "exception", "error": str(exc)},
                "report_url": None,
                "scanned_at": datetime.now(timezone.utc),
            }

        await cls._register_success()

        attributes = raw.get("data", {}).get("attributes", {})
        stats = attributes.get("last_analysis_stats", {})
        malicious = int(stats.get("malicious", 0))
        suspicious = int(stats.get("suspicious", 0))
        harmless = int(stats.get("harmless", 0))
        total = max(malicious + suspicious + harmless, 1)
        score = float((malicious * 1.0 + suspicious * 0.5) / total)

        if malicious > 0:
            verdict = "fail"
        elif suspicious > 0:
            verdict = "warn"
        else:
            verdict = "pass"

        return {
            "engine": "virustotal",
            "verdict": verdict,
            "score": score,
            "raw_json": {
                "sha256": sha256,
                "malicious": malicious,
                "suspicious": suspicious,
                "harmless": harmless,
                "stats": stats,
            },
            "report_url": f"https://www.virustotal.com/gui/file/{sha256}",
            "scanned_at": datetime.now(timezone.utc),
        }


class PolicyScanner:
    """Rule-based prompt/policy scanner for risky instruction patterns."""

    _PATTERNS: list[tuple[str, str, float]] = [
        ("exfiltration", r"(export|exfiltrat|send).*(token|secret|credential|password)", 0.9),
        ("privilege_bypass", r"(bypass|ignore|disable).*(permission|auth|rbac|policy)", 0.8),
        ("safety_override", r"(ignore|override).*(safety|guardrail|system instruction)", 0.9),
        ("hidden_channel", r"(base64|steganography|hidden channel|covert)", 0.5),
        ("command_exec", r"(rm\s+-rf|curl\s+.+\|\s*sh|powershell\s+-enc)", 1.0),
    ]

    @classmethod
    def scan_text(cls, text: str) -> dict[str, Any]:
        """Return structured flags and severity score for a skill document."""
        lowered = text.lower()
        flags: list[dict[str, Any]] = []
        max_score = 0.0

        for label, pattern, weight in cls._PATTERNS:
            if re.search(pattern, lowered):
                flags.append({"label": label, "pattern": pattern, "weight": weight})
                max_score = max(max_score, weight)

        if max_score >= 0.9:
            verdict = "fail"
        elif max_score >= 0.5:
            verdict = "warn"
        else:
            verdict = "pass"

        return {
            "engine": "policy",
            "verdict": verdict,
            "score": max_score,
            "raw_json": {"flags": flags, "count": len(flags)},
            "report_url": None,
            "scanned_at": datetime.now(timezone.utc),
        }


class SkillService:
    """Service methods for skill catalog workflow."""

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    async def create_skill_with_version(
        session: AsyncSession,
        *,
        slug: str,
        name: str,
        description: str,
        owner_user_id: str,
        owner_type: str,
        metadata_json: dict[str, Any],
        skill_markdown: str,
        submitted_by: str,
        status: str = "pending_scan",
    ) -> Skill:
        """Create a skill and immutable version in one transaction."""
        now = SkillService._now()
        normalized_slug = slug.strip().lower()
        existing = await session.execute(select(Skill).where(Skill.slug == normalized_slug))
        skill = existing.scalar_one_or_none()
        from_status = "draft"
        if skill is None:
            skill = Skill(
                slug=normalized_slug,
                name=name,
                description=description,
                owner_user_id=owner_user_id,
                owner_type=owner_type,
                status=status,
                visibility="private",
                risk_label="medium",
                is_new=False,
                new_until=None,
                created_at=now,
                updated_at=now,
            )
            session.add(skill)
            await session.flush()
        else:
            if skill.owner_user_id != owner_user_id:
                raise ValueError("Skill slug is already owned by another user")
            from_status = skill.status
            skill.name = name
            skill.description = description
            skill.status = status
            skill.visibility = "private"
            skill.is_new = False
            skill.new_until = None
            skill.updated_at = now

        content_sha256 = hashlib.sha256(skill_markdown.encode("utf-8")).hexdigest()
        latest_version = await SkillService.latest_version(session, skill.id)
        next_version = (latest_version.version + 1) if latest_version else 1
        version = SkillVersion(
            skill_id=skill.id,
            version=next_version,
            content_sha256=content_sha256,
            storage_url=f"inline://skill_versions/{content_sha256}",
            metadata_json=json.dumps({"metadata": metadata_json, "skill_md": skill_markdown}),
            created_by=submitted_by,
            created_at=now,
        )
        session.add(version)
        await session.flush()

        event = SkillPublishEvent(
            skill_id=skill.id,
            skill_version_id=version.id,
            from_status=from_status,
            to_status=status,
            actor_id=submitted_by,
            actor_type=owner_type,
            reason="initial_submission",
            created_at=now,
        )
        session.add(event)
        await session.flush()
        await session.refresh(skill)
        return skill

    @staticmethod
    async def latest_version(session: AsyncSession, skill_id: str) -> SkillVersion | None:
        """Return the latest immutable version for a skill."""
        result = await session.execute(
            select(SkillVersion).where(SkillVersion.skill_id == skill_id).order_by(desc(SkillVersion.version)).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def run_scans_for_skill(session: AsyncSession, *, skill_id: str, actor_id: str, actor_type: str) -> dict[str, Any]:
        """Run VirusTotal and policy scans for the latest version and transition workflow state."""
        skill = await session.get(Skill, skill_id)
        if skill is None:
            raise ValueError("Skill not found")

        version = await SkillService.latest_version(session, skill_id)
        if version is None:
            raise ValueError("Skill version not found")

        try:
            payload = json.loads(version.metadata_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid skill metadata JSON") from exc
        skill_md = str(payload.get("skill_md", ""))

        vt_result = await VirusTotalScanner.scan_content(file_name=f"{skill.slug}.md", content=skill_md.encode("utf-8"))
        policy_result = PolicyScanner.scan_text(skill_md)

        now = SkillService._now()
        session.add(
            SkillScanResult(
                skill_version_id=version.id,
                engine="virustotal",
                verdict=vt_result["verdict"],
                score=vt_result["score"],
                raw_json=json.dumps(vt_result["raw_json"]),
                report_url=vt_result["report_url"],
                scanned_at=vt_result["scanned_at"],
                created_at=now,
            )
        )
        session.add(
            SkillScanResult(
                skill_version_id=version.id,
                engine="policy",
                verdict=policy_result["verdict"],
                score=policy_result["score"],
                raw_json=json.dumps(policy_result["raw_json"]),
                report_url=None,
                scanned_at=policy_result["scanned_at"],
                created_at=now,
            )
        )

        max_score = max(vt_result["score"], policy_result["score"])
        risk = "low"
        if max_score >= 0.9:
            risk = "critical"
        elif max_score >= 0.7:
            risk = "high"
        elif max_score >= 0.4:
            risk = "medium"

        from_status = skill.status
        target_status = "pending_review"
        if vt_result["verdict"] == "error" and policy_result["verdict"] == "error":
            target_status = "pending_scan"
        skill.status = target_status
        skill.risk_label = risk
        skill.updated_at = now

        session.add(
            SkillPublishEvent(
                skill_id=skill.id,
                skill_version_id=version.id,
                from_status=from_status,
                to_status=target_status,
                actor_id=actor_id,
                actor_type=actor_type,
                reason="scan_completed" if target_status == "pending_review" else "scan_failed_retry_required",
                created_at=now,
            )
        )
        await session.flush()
        return {"skill_id": skill.id, "version_id": version.id, "vt": vt_result, "policy": policy_result}

    @staticmethod
    async def get_review_queue(session: AsyncSession) -> list[dict[str, Any]]:
        """Return pending-review skills with latest scan context for admin moderation."""
        rows = await session.execute(
            select(Skill).where(Skill.status == "pending_review").order_by(Skill.updated_at.desc())
        )
        queue: list[dict[str, Any]] = []
        for skill in rows.scalars().all():
            version = await SkillService.latest_version(session, skill.id)
            if version is None:
                continue
            scans = await session.execute(
                select(SkillScanResult).where(SkillScanResult.skill_version_id == version.id).order_by(SkillScanResult.scanned_at.desc())
            )
            queue.append(
                {
                    "skill": skill,
                    "version": version,
                    "scans": scans.scalars().all(),
                }
            )
        return queue

    @staticmethod
    async def apply_review_decision(
        session: AsyncSession,
        *,
        skill_id: str,
        reviewer_admin_id: str,
        decision: str,
        notes: str | None,
    ) -> Skill:
        """Apply admin review decision and persist audit/review rows."""
        skill = await session.get(Skill, skill_id)
        if skill is None:
            raise ValueError("Skill not found")

        version = await SkillService.latest_version(session, skill_id)
        if version is None:
            raise ValueError("Skill version not found")

        now = SkillService._now()
        from_status = skill.status

        if decision == "approve_internal":
            skill.status = "approved_internal"
            skill.visibility = "global"
            skill.is_new = True
            skill.new_until = now + timedelta(days=7)
        elif decision == "approve_marketplace":
            skill.status = "approved_marketplace"
            skill.visibility = "hub"
            skill.is_new = True
            skill.new_until = now + timedelta(days=7)
        elif decision == "reject":
            skill.status = "rejected"
            skill.is_new = False
            skill.new_until = None
        elif decision == "needs_changes":
            skill.status = "draft"
            skill.visibility = "private"
            skill.is_new = False
            skill.new_until = None
        else:
            raise ValueError("Unsupported decision")

        skill.updated_at = now

        session.add(
            SkillReview(
                skill_version_id=version.id,
                reviewer_admin_id=reviewer_admin_id,
                decision=decision,
                notes=notes,
                reviewed_at=now,
                created_at=now,
            )
        )
        session.add(
            SkillPublishEvent(
                skill_id=skill.id,
                skill_version_id=version.id,
                from_status=from_status,
                to_status=skill.status,
                actor_id=reviewer_admin_id,
                actor_type="admin",
                reason=notes or decision,
                created_at=now,
            )
        )
        await session.flush()
        await session.refresh(skill)
        return skill

    @staticmethod
    async def expire_new_flags(session: AsyncSession) -> int:
        """Unset NEW badges after expiry threshold."""
        now = SkillService._now()
        rows = await session.execute(
            select(Skill).where(and_(Skill.is_new.is_(True), Skill.new_until.is_not(None), Skill.new_until < now))
        )
        count = 0
        for skill in rows.scalars().all():
            skill.is_new = False
            skill.updated_at = now
            count += 1
        return count

    @staticmethod
    async def list_visibility(session: AsyncSession, *, visibility: str) -> list[dict[str, Any]]:
        """List approved skills by visibility target, with creator context for hub."""
        await SkillService.expire_new_flags(session)
        approved_status = "approved_internal" if visibility == "global" else "approved_marketplace"
        rows = await session.execute(
            select(Skill, User)
            .join(User, User.uid == Skill.owner_user_id, isouter=True)
            .where(and_(Skill.visibility == visibility, Skill.status == approved_status))
            .order_by(Skill.updated_at.desc())
        )
        payload: list[dict[str, Any]] = []
        for skill, owner in rows.all():
            payload.append(
                {
                    "id": skill.id,
                    "slug": skill.slug,
                    "name": skill.name,
                    "description": skill.description,
                    "visibility": skill.visibility,
                    "status": skill.status,
                    "risk_label": skill.risk_label,
                    "is_new": skill.is_new,
                    "new_until": skill.new_until,
                    "owner": {
                        "user_id": skill.owner_user_id,
                        "name": getattr(owner, "name", None),
                        "avatar_url": getattr(owner, "avatar_url", None),
                    },
                    "updated_at": skill.updated_at,
                }
            )
        return payload

    @staticmethod
    async def list_user_skills(session: AsyncSession, *, user_id: str) -> list[Skill]:
        """List all skills submitted by a given user."""
        rows = await session.execute(select(Skill).where(Skill.owner_user_id == user_id).order_by(Skill.updated_at.desc()))
        return rows.scalars().all()

    @staticmethod
    async def list_active_skills(session: AsyncSession, *, requested_for_user_id: str) -> list[dict[str, Any]]:
        """Return globally active, compliant skills for runtime injection."""
        await SkillService.expire_new_flags(session)
        rows = await session.execute(
            select(Skill).where(
                and_(
                    Skill.status.in_(["approved_internal", "approved_marketplace"]),
                    Skill.visibility.in_(["global", "hub"]),
                )
            )
        )
        active: list[dict[str, Any]] = []
        for skill in rows.scalars().all():
            version = await SkillService.latest_version(session, skill.id)
            if version is None:
                continue

            scans = await session.execute(
                select(SkillScanResult).where(SkillScanResult.skill_version_id == version.id)
            )
            by_engine = {scan.engine: scan for scan in scans.scalars().all()}
            vt_scan = by_engine.get("virustotal")
            vt_verdict = vt_scan.verdict if vt_scan else None
            if settings.VIRUSTOTAL_REQUIRED:
                vt_ok = vt_verdict in {"pass", "warn"}
            else:
                vt_ok = vt_verdict in {"pass", "warn", "skipped"}
                if vt_verdict == "skipped":
                    logger.warning(
                        "Skill %s is runtime-compliant with skipped VT scan because VIRUSTOTAL_REQUIRED=false",
                        skill.id,
                    )
            policy_ok = by_engine.get("policy") and by_engine["policy"].verdict in {"pass", "warn"}
            if not (vt_ok and policy_ok):
                continue

            try:
                payload = json.loads(version.metadata_json or "{}")
            except json.JSONDecodeError:
                logger.warning("Skipping skill %s with corrupted metadata_json", skill.id)
                continue
            active.append(
                {
                    "skill_id": skill.id,
                    "slug": skill.slug,
                    "name": skill.name,
                    "version": version.version,
                    "content_sha256": version.content_sha256,
                    "provenance": {
                        "owner_user_id": skill.owner_user_id,
                        "visibility": skill.visibility,
                        "approved_status": skill.status,
                        "for_user_id": requested_for_user_id,
                    },
                    "skill_md": payload.get("skill_md", ""),
                }
            )
        return active
