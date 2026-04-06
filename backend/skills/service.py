"""Business logic for secure skill publication, installation, and runtime gating."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import and_, delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.database import (
    Skill,
    SkillAuditEvent,
    SkillInstall,
    SkillReview,
    SkillScanResult,
    SkillSubmission,
    SkillVersion,
    User,
)
from config import settings

logger = logging.getLogger(__name__)

APPROVED_STATUSES = {"published_global", "published_hub"}
REVIEW_SLA_MESSAGE = "Review SLA: up to 5 working days."


class VirusTotalScanner:
    """Thin VT client with timeout/retry and a simple circuit breaker."""

    _consecutive_failures = 0
    _opened_until: datetime | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def _is_open(cls) -> bool:
        async with cls._lock:
            return cls._opened_until is not None and datetime.now(timezone.utc) < cls._opened_until

    @classmethod
    async def _register_failure(cls) -> None:
        async with cls._lock:
            cls._consecutive_failures += 1
            if cls._consecutive_failures >= 3:
                cls._opened_until = datetime.now(timezone.utc) + timedelta(minutes=5)

    @classmethod
    async def _register_success(cls) -> None:
        async with cls._lock:
            cls._consecutive_failures = 0
            cls._opened_until = None

    @classmethod
    async def scan_content(cls, *, file_name: str, content: bytes) -> dict[str, Any]:
        """Run VirusTotal hash lookup/upload flow and return normalized payload."""
        if not settings.VIRUSTOTAL_API_KEY:
            return {
                "engine": "virustotal",
                "verdict": "skipped",
                "risk_label": "low",
                "raw_json": {"reason": "missing_api_key"},
                "report_url": None,
                "scanned_at": datetime.now(timezone.utc),
            }

        if len(content) > settings.VIRUSTOTAL_MAX_FILE_BYTES:
            return {
                "engine": "virustotal",
                "verdict": "error",
                "risk_label": "critical",
                "raw_json": {"reason": "file_too_large", "max_bytes": settings.VIRUSTOTAL_MAX_FILE_BYTES},
                "report_url": None,
                "scanned_at": datetime.now(timezone.utc),
            }

        if await cls._is_open():
            return {
                "engine": "virustotal",
                "verdict": "error",
                "risk_label": "high",
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
                    raw: dict[str, Any] = {}
                    if analysis_id:
                        for _ in range(settings.VIRUSTOTAL_MAX_POLLS):
                            poll_response = await client.get(f"https://www.virustotal.com/api/v3/analyses/{analysis_id}")
                            poll_response.raise_for_status()
                            raw = poll_response.json()
                            final_status = raw.get("data", {}).get("attributes", {}).get("status", "queued")
                            if final_status == "completed":
                                break
                            await asyncio.sleep(settings.VIRUSTOTAL_POLL_INTERVAL_SECONDS)
                    if final_status != "completed":
                        return {
                            "engine": "virustotal",
                            "verdict": "error",
                            "risk_label": "high",
                            "raw_json": {"reason": "analysis_timeout", "last_status": final_status},
                            "report_url": None,
                            "scanned_at": datetime.now(timezone.utc),
                        }
                else:
                    file_report.raise_for_status()
                    raw = file_report.json()
        except (httpx.RequestError, httpx.HTTPStatusError, OSError) as exc:
            await cls._register_failure()
            logger.warning("VirusTotal scan failed: %s", exc)
            return {
                "engine": "virustotal",
                "verdict": "error",
                "risk_label": "high",
                "raw_json": {"reason": "exception", "error": str(exc)},
                "report_url": None,
                "scanned_at": datetime.now(timezone.utc),
            }

        await cls._register_success()

        attributes = raw.get("data", {}).get("attributes", {})
        stats = attributes.get("last_analysis_stats") or attributes.get("stats", {})
        malicious = int(stats.get("malicious", 0))
        suspicious = int(stats.get("suspicious", 0))

        if malicious > 0:
            verdict = "fail"
            risk = "critical"
        elif suspicious > 0:
            verdict = "warn"
            risk = "medium"
        else:
            verdict = "pass"
            risk = "low"

        return {
            "engine": "virustotal",
            "verdict": verdict,
            "risk_label": risk,
            "raw_json": {"sha256": sha256, "stats": stats},
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
        """Return structured flags and risk label for a skill document."""
        lowered = text.lower()
        flags: list[dict[str, Any]] = []
        max_score = 0.0

        for label, pattern, weight in cls._PATTERNS:
            if re.search(pattern, lowered, flags=re.IGNORECASE | re.DOTALL):
                flags.append({"label": label, "pattern": pattern, "weight": weight})
                max_score = max(max_score, weight)

        if max_score >= 0.9:
            verdict = "fail"
            risk = "critical"
        elif max_score >= 0.5:
            verdict = "warn"
            risk = "medium"
        else:
            verdict = "pass"
            risk = "low"

        return {
            "engine": "policy",
            "verdict": verdict,
            "risk_label": risk,
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
    async def emit_notification_hook(
        *,
        event_type: str,
        recipient_user_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Phase 1 placeholder notification hook for email/in-app adapters."""
        logger.info(
            "Skill notification hook emitted: event=%s recipient=%s payload=%s",
            event_type,
            recipient_user_id,
            payload,
        )

    @staticmethod
    async def latest_version(session: AsyncSession, skill_id: str) -> SkillVersion | None:
        result = await session.execute(
            select(SkillVersion).where(SkillVersion.skill_id == skill_id).order_by(desc(SkillVersion.version)).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _record_event(
        session: AsyncSession,
        *,
        skill_id: str,
        version_id: str,
        submission_id: str | None,
        from_status: str,
        to_status: str,
        actor_id: str,
        actor_type: str,
        reason: str,
        event_type: str = "transition",
    ) -> None:
        session.add(
            SkillAuditEvent(
                skill_id=skill_id,
                submission_id=submission_id,
                skill_version_id=version_id,
                from_status=from_status,
                to_status=to_status,
                actor_id=actor_id,
                actor_type=actor_type,
                reason=reason,
                event_type=event_type,
                created_at=SkillService._now(),
            )
        )

    @staticmethod
    async def save_draft(
        session: AsyncSession,
        *,
        slug: str,
        name: str,
        description: str,
        owner_user_id: str,
        owner_type: str,
        publish_target: str,
        metadata_json: dict[str, Any],
        skill_markdown: str,
        submitted_by: str,
    ) -> tuple[Skill, SkillSubmission]:
        """Create/update a skill draft and append immutable version history."""
        now = SkillService._now()
        normalized_slug = slug.strip().lower()
        existing = await session.execute(select(Skill).where(Skill.slug == normalized_slug))
        skill = existing.scalar_one_or_none()

        submission_type = "new"
        from_status = "draft"
        if skill is None:
            skill = Skill(
                slug=normalized_slug,
                name=name,
                description=description,
                owner_user_id=owner_user_id,
                owner_type=owner_type,
                publish_target=publish_target,
                status="draft",
                risk_label="low",
                is_new=False,
                new_until=None,
                created_at=now,
                updated_at=now,
            )
            session.add(skill)
            await session.flush()
        else:
            if skill.owner_user_id != owner_user_id:
                raise ValueError("You do not own this skill slug")
            submission_type = "update"
            from_status = skill.status
            skill.name = name
            skill.description = description
            skill.publish_target = publish_target
            skill.status = "draft"
            skill.updated_at = now

        latest_version = await SkillService.latest_version(session, skill.id)
        next_version = (latest_version.version + 1) if latest_version else 1
        content_sha256 = hashlib.sha256(skill_markdown.encode("utf-8")).hexdigest()

        version = SkillVersion(
            skill_id=skill.id,
            version=next_version,
            content_sha256=content_sha256,
            storage_path=f"inline://skill_versions/{content_sha256}",
            metadata_json=json.dumps({"metadata": metadata_json, "skill_md": skill_markdown}),
            created_by=submitted_by,
            created_at=now,
        )
        session.add(version)
        await session.flush()

        submission = SkillSubmission(
            skill_id=skill.id,
            version_id=version.id,
            submitted_by=submitted_by,
            submission_type=submission_type,
            review_state="draft",
            created_at=now,
            updated_at=now,
        )
        session.add(submission)
        await session.flush()

        await SkillService._record_event(
            session,
            skill_id=skill.id,
            version_id=version.id,
            submission_id=submission.id,
            from_status=from_status,
            to_status="draft",
            actor_id=submitted_by,
            actor_type=owner_type,
            reason="saved_draft",
        )
        await session.flush()
        await session.refresh(skill)
        return skill, submission

    @staticmethod
    async def submit_skill(
        session: AsyncSession,
        *,
        slug: str,
        name: str,
        description: str,
        owner_user_id: str,
        owner_type: str,
        publish_target: str,
        metadata_json: dict[str, Any],
        skill_markdown: str,
        submitted_by: str,
    ) -> tuple[Skill, SkillSubmission]:
        """Create/update a skill, append immutable version, and queue submission."""
        now = SkillService._now()
        normalized_slug = slug.strip().lower()
        existing = await session.execute(select(Skill).where(Skill.slug == normalized_slug))
        skill = existing.scalar_one_or_none()

        submission_type = "new"
        from_status = "draft"
        if skill is None:
            skill = Skill(
                slug=normalized_slug,
                name=name,
                description=description,
                owner_user_id=owner_user_id,
                owner_type=owner_type,
                publish_target=publish_target,
                status="submitted",
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
                raise ValueError("You do not own this skill slug")
            submission_type = "update"
            from_status = skill.status
            skill.name = name
            skill.description = description
            skill.publish_target = publish_target
            skill.status = "submitted"
            skill.is_new = False
            skill.new_until = None
            skill.updated_at = now

        latest_version = await SkillService.latest_version(session, skill.id)
        next_version = (latest_version.version + 1) if latest_version else 1
        content_sha256 = hashlib.sha256(skill_markdown.encode("utf-8")).hexdigest()

        version = SkillVersion(
            skill_id=skill.id,
            version=next_version,
            content_sha256=content_sha256,
            storage_path=f"inline://skill_versions/{content_sha256}",
            metadata_json=json.dumps({"metadata": metadata_json, "skill_md": skill_markdown}),
            created_by=submitted_by,
            created_at=now,
        )
        session.add(version)
        await session.flush()

        submission = SkillSubmission(
            skill_id=skill.id,
            version_id=version.id,
            submitted_by=submitted_by,
            submission_type=submission_type,
            review_state="submitted",
            created_at=now,
            updated_at=now,
        )
        session.add(submission)
        await session.flush()

        await SkillService._record_event(
            session,
            skill_id=skill.id,
            version_id=version.id,
            submission_id=submission.id,
            from_status=from_status,
            to_status="submitted",
            actor_id=submitted_by,
            actor_type=owner_type,
            reason="submitted",
        )
        await SkillService.emit_notification_hook(
            event_type="skill_submitted",
            recipient_user_id=owner_user_id,
            payload={
                "skill_id": skill.id,
                "submission_id": submission.id,
                "status": "submitted",
                "sla_message": REVIEW_SLA_MESSAGE,
            },
        )
        await session.flush()
        await session.refresh(skill)
        return skill, submission

    @staticmethod
    async def run_scans_for_submission(
        session: AsyncSession,
        *,
        submission_id: str,
        actor_id: str,
        actor_type: str,
    ) -> dict[str, Any]:
        """Run VT then policy scan and move state machine forward."""
        submission = await session.get(SkillSubmission, submission_id)
        if submission is None:
            raise ValueError("Submission not found")

        skill = await session.get(Skill, submission.skill_id)
        version = await session.get(SkillVersion, submission.version_id)
        if skill is None or version is None:
            raise ValueError("Submission references missing skill/version")

        try:
            payload = json.loads(version.metadata_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid skill metadata JSON") from exc
        skill_md = str(payload.get("skill_md", ""))

        now = SkillService._now()

        from_status = skill.status
        skill.status = "scanning"
        submission.review_state = "scanning"

        vt_result = await VirusTotalScanner.scan_content(file_name=f"{skill.slug}.md", content=skill_md.encode("utf-8"))
        session.add(
            SkillScanResult(
                skill_version_id=version.id,
                engine="virustotal",
                verdict=vt_result["verdict"],
                risk_label=vt_result["risk_label"],
                raw_json=json.dumps(vt_result["raw_json"]),
                report_url=vt_result["report_url"],
                scanned_at=vt_result["scanned_at"],
                created_at=now,
            )
        )

        if vt_result["verdict"] == "error":
            skill.status = "scanning"
            submission.review_state = "scanning"
            await SkillService._record_event(
                session,
                skill_id=skill.id,
                version_id=version.id,
                submission_id=submission.id,
                from_status=from_status,
                to_status="scanning",
                actor_id=actor_id,
                actor_type=actor_type,
                reason="vt_scan_error",
            )
            await session.flush()
            return {"skill_id": skill.id, "submission_id": submission.id, "version_id": version.id, "vt": vt_result}

        skill.status = "scanning"
        submission.review_state = "scanning"

        policy_result = PolicyScanner.scan_text(skill_md)
        session.add(
            SkillScanResult(
                skill_version_id=version.id,
                engine="policy",
                verdict=policy_result["verdict"],
                risk_label=policy_result["risk_label"],
                raw_json=json.dumps(policy_result["raw_json"]),
                report_url=None,
                scanned_at=policy_result["scanned_at"],
                created_at=now,
            )
        )

        skill.risk_label = "critical" if "critical" in {vt_result["risk_label"], policy_result["risk_label"]} else (
            "high" if "high" in {vt_result["risk_label"], policy_result["risk_label"]} else (
                "medium" if "medium" in {vt_result["risk_label"], policy_result["risk_label"]} else "low"
            )
        )
        skill.status = "review"
        submission.review_state = "review"
        skill.updated_at = now
        submission.updated_at = now

        await SkillService._record_event(
            session,
            skill_id=skill.id,
            version_id=version.id,
            submission_id=submission.id,
            from_status=from_status,
            to_status="review",
            actor_id=actor_id,
            actor_type=actor_type,
            reason="scan_and_policy_complete",
        )
        await session.flush()
        return {
            "skill_id": skill.id,
            "submission_id": submission.id,
            "version_id": version.id,
            "vt": vt_result,
            "policy": policy_result,
        }

    @staticmethod
    async def get_review_queue(session: AsyncSession) -> list[dict[str, Any]]:
        rows = await session.execute(
            select(SkillSubmission, Skill, SkillVersion)
            .join(Skill, Skill.id == SkillSubmission.skill_id)
            .join(SkillVersion, SkillVersion.id == SkillSubmission.version_id)
            .where(SkillSubmission.review_state.in_(["submitted", "scanning", "review"]))
            .order_by(SkillSubmission.created_at.asc())
        )
        queue_rows = rows.all()
        version_ids = [version.id for _, _, version in queue_rows]
        scans_by_version_id: dict[str, list[SkillScanResult]] = {version_id: [] for version_id in version_ids}

        if version_ids:
            scan_rows = await session.execute(
                select(SkillScanResult)
                .where(SkillScanResult.skill_version_id.in_(version_ids))
                .order_by(desc(SkillScanResult.scanned_at), desc(SkillScanResult.created_at))
            )
            for scan in scan_rows.scalars().all():
                scans_by_version_id.setdefault(scan.skill_version_id, []).append(scan)

        queue: list[dict[str, Any]] = []
        for submission, skill, version in queue_rows:
            queue.append(
                {
                    "submission": submission,
                    "skill": skill,
                    "version": version,
                    "scans": scans_by_version_id.get(version.id, []),
                }
            )
        return queue

    @staticmethod
    async def apply_review_decision(
        session: AsyncSession,
        *,
        submission_id: str,
        reviewer_admin_id: str,
        decision: str,
        notes: str | None,
    ) -> Skill:
        """Apply human moderation decision to submission and parent skill."""
        submission = await session.get(SkillSubmission, submission_id)
        if submission is None:
            raise ValueError("Submission not found")

        skill = await session.get(Skill, submission.skill_id)
        if skill is None:
            raise ValueError("Skill not found")
        if skill.owner_user_id == reviewer_admin_id:
            raise ValueError("Creator cannot self-approve")

        version = await session.get(SkillVersion, submission.version_id)
        if version is None:
            raise ValueError("Skill version not found")

        now = SkillService._now()
        from_status = skill.status

        if decision == "approve_global":
            skill.status = "published_global"
            skill.publish_target = "global"
            skill.is_new = True
            skill.new_until = now + timedelta(days=7)
            submission.review_state = "published_global"
        elif decision == "approve_hub":
            skill.status = "published_hub"
            skill.publish_target = "hub"
            skill.is_new = True
            skill.new_until = now + timedelta(days=7)
            submission.review_state = "published_hub"
        elif decision == "reject":
            skill.status = "rejected"
            skill.is_new = False
            skill.new_until = None
            submission.review_state = "rejected"
        elif decision == "needs_changes":
            skill.status = "draft"
            skill.is_new = False
            skill.new_until = None
            submission.review_state = "draft"
        else:
            raise ValueError("Unsupported decision")

        skill.updated_at = now
        submission.updated_at = now

        session.add(
            SkillReview(
                skill_version_id=version.id,
                submission_id=submission.id,
                reviewer_admin_id=reviewer_admin_id,
                decision=decision,
                notes=notes,
                reviewed_at=now,
                created_at=now,
            )
        )
        await SkillService._record_event(
            session,
            skill_id=skill.id,
            version_id=version.id,
            submission_id=submission.id,
            from_status=from_status,
            to_status=skill.status,
            actor_id=reviewer_admin_id,
            actor_type="admin",
            reason=notes or decision,
        )
        await SkillService.emit_notification_hook(
            event_type="skill_reviewed",
            recipient_user_id=skill.owner_user_id,
            payload={
                "skill_id": skill.id,
                "submission_id": submission.id,
                "decision": decision,
                "status": skill.status,
            },
        )
        await session.flush()
        await session.refresh(skill)
        return skill

    @staticmethod
    async def expire_new_flags(session: AsyncSession) -> int:
        now = SkillService._now()
        rows = await session.execute(select(Skill).where(and_(Skill.is_new.is_(True), Skill.new_until.is_not(None), Skill.new_until < now)))
        count = 0
        for skill in rows.scalars().all():
            skill.is_new = False
            skill.updated_at = now
            count += 1
        return count

    @staticmethod
    async def list_catalog(session: AsyncSession, *, publish_target: str) -> list[dict[str, Any]]:
        approved_status = "published_global" if publish_target == "global" else "published_hub"
        rows = await session.execute(
            select(Skill, User)
            .join(User, User.uid == Skill.owner_user_id, isouter=True)
            .where(and_(Skill.publish_target == publish_target, Skill.status == approved_status))
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
                    "publish_target": skill.publish_target,
                    "status": skill.status,
                    "risk_label": skill.risk_label,
                    "is_new": skill.is_new,
                    "new_until": skill.new_until,
                    "owner": {
                        "user_id": skill.owner_user_id,
                        "username": getattr(owner, "name", None) or (getattr(owner, "email", None) or "").split("@")[0],
                        "name": getattr(owner, "name", None),
                        "avatar_url": getattr(owner, "avatar_url", None),
                    },
                    "updated_at": skill.updated_at,
                }
            )
        return payload

    @staticmethod
    async def install_skill(session: AsyncSession, *, user_id: str, skill_id: str) -> SkillInstall:
        skill = await session.get(Skill, skill_id)
        if skill is None:
            raise ValueError("Skill not found")
        if skill.status not in APPROVED_STATUSES:
            raise ValueError("Skill is not approved for installation")

        version = await SkillService.latest_version(session, skill_id)
        if version is None:
            raise ValueError("Approved skill is missing version")

        rows = await session.execute(select(SkillInstall).where(and_(SkillInstall.user_id == user_id, SkillInstall.skill_id == skill_id)))
        install = rows.scalar_one_or_none()
        now = SkillService._now()
        if install is None:
            install = SkillInstall(
                user_id=user_id,
                skill_id=skill_id,
                skill_version_id=version.id,
                enabled=True,
                installed_at=now,
                updated_at=now,
            )
            try:
                async with session.begin_nested():
                    session.add(install)
                    await session.flush()
            except IntegrityError:
                rows = await session.execute(
                    select(SkillInstall).where(and_(SkillInstall.user_id == user_id, SkillInstall.skill_id == skill_id))
                )
                install = rows.scalar_one_or_none()
                if install is None:
                    raise
                install.skill_version_id = version.id
                install.enabled = True
                install.updated_at = now
                await session.flush()
        else:
            install.skill_version_id = version.id
            install.enabled = True
            install.updated_at = now
            await session.flush()
        return install

    @staticmethod
    async def uninstall_skill(session: AsyncSession, *, user_id: str, skill_id: str) -> int:
        result = await session.execute(delete(SkillInstall).where(and_(SkillInstall.user_id == user_id, SkillInstall.skill_id == skill_id)))
        return int(result.rowcount or 0)

    @staticmethod
    async def set_skill_enabled(session: AsyncSession, *, user_id: str, skill_id: str, enabled: bool) -> SkillInstall:
        rows = await session.execute(select(SkillInstall).where(and_(SkillInstall.user_id == user_id, SkillInstall.skill_id == skill_id)))
        install = rows.scalar_one_or_none()
        if install is None:
            raise ValueError("Skill is not installed")
        install.enabled = enabled
        install.updated_at = SkillService._now()
        await session.flush()
        return install

    @staticmethod
    async def list_installed_skills(session: AsyncSession, *, user_id: str) -> list[dict[str, Any]]:
        rows = await session.execute(
            select(SkillInstall, Skill, SkillVersion)
            .join(Skill, Skill.id == SkillInstall.skill_id)
            .join(SkillVersion, SkillVersion.id == SkillInstall.skill_version_id)
            .where(SkillInstall.user_id == user_id)
            .order_by(desc(SkillInstall.updated_at))
        )
        payload: list[dict[str, Any]] = []
        for install, skill, version in rows.all():
            payload.append(
                {
                    "skill_id": skill.id,
                    "version_id": version.id,
                    "slug": skill.slug,
                    "name": skill.name,
                    "publish_target": skill.publish_target,
                    "risk_label": skill.risk_label,
                    "status": skill.status,
                    "enabled": install.enabled,
                    "installed_at": install.installed_at,
                    "updated_at": install.updated_at,
                }
            )
        return payload

    @staticmethod
    async def list_skill_history(session: AsyncSession, *, skill_id: str) -> list[SkillAuditEvent]:
        rows = await session.execute(
            select(SkillAuditEvent).where(SkillAuditEvent.skill_id == skill_id).order_by(desc(SkillAuditEvent.created_at))
        )
        return rows.scalars().all()
