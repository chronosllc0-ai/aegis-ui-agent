"""Service layer for Skill Hub deterministic state transitions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Skill, SkillHubSubmission, SkillHubTransition

_ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("submitted",),
    "submitted": ("under_review",),
    "under_review": ("changes_requested", "approved", "rejected"),
    "changes_requested": ("submitted",),
    "approved": ("published",),
    "published": ("suspended", "archived"),
    "suspended": ("published", "archived"),
    "archived": (),
    "rejected": (),
}


class SkillHubService:
    """Business logic for hub submission lifecycle and audit history."""

    @staticmethod
    def now() -> datetime:
        """Return current UTC timestamp."""
        return datetime.now(timezone.utc)

    @staticmethod
    def allowed_transitions(current_state: str) -> tuple[str, ...]:
        """Return valid next states from current state."""
        return _ALLOWED_TRANSITIONS.get(current_state, ())

    @staticmethod
    async def create_submission(
        session: AsyncSession,
        *,
        submitter_id: str,
        skill_id: str | None,
        skill_slug: str,
        title: str,
        description: str,
        risk_label: str,
        previous_submission_id: str | None,
        submit_now: bool,
    ) -> SkillHubSubmission:
        """Create a submission revision and optional immediate submit transition."""
        revision = 1
        if previous_submission_id:
            previous = await session.get(SkillHubSubmission, previous_submission_id)
            if previous is None:
                raise ValueError("Previous submission not found")
            revision = previous.revision + 1

        submission = SkillHubSubmission(
            skill_id=skill_id,
            skill_slug=skill_slug,
            title=title,
            description=description,
            risk_label=risk_label,
            revision=revision,
            submitted_by=submitter_id,
            current_state="draft",
            reviewer_notes_json="[]",
            created_at=SkillHubService.now(),
            updated_at=SkillHubService.now(),
        )
        session.add(submission)
        await session.flush()

        session.add(
            SkillHubTransition(
                submission_id=submission.id,
                from_state="draft",
                to_state="draft",
                actor_id=submitter_id,
                actor_role="user",
                notes="Submission draft created",
                created_at=SkillHubService.now(),
            )
        )

        if submit_now:
            await SkillHubService.transition_submission(
                session,
                submission_id=submission.id,
                actor_id=submitter_id,
                actor_role="user",
                next_state="submitted",
                notes="Submitted for review",
            )

        return submission

    @staticmethod
    async def transition_submission(
        session: AsyncSession,
        *,
        submission_id: str,
        actor_id: str,
        actor_role: str,
        next_state: str,
        notes: str | None,
    ) -> SkillHubSubmission:
        """Apply a deterministic state transition with role and audit enforcement."""
        submission = await session.get(SkillHubSubmission, submission_id)
        if submission is None:
            raise ValueError("Submission not found")

        allowed_next = SkillHubService.allowed_transitions(submission.current_state)
        if next_state not in allowed_next:
            raise ValueError(f"Illegal transition: {submission.current_state} -> {next_state}")

        user_allowed = {
            ("draft", "submitted"),
            ("changes_requested", "submitted"),
        }
        if actor_role not in {"admin", "superadmin"} and (submission.current_state, next_state) not in user_allowed:
            raise PermissionError("Admin access required for this transition")

        if actor_role not in {"admin", "superadmin"} and submission.submitted_by != actor_id:
            raise PermissionError("Cannot modify another user's submission")

        from_state = submission.current_state
        submission.current_state = next_state
        submission.updated_at = SkillHubService.now()

        if notes and next_state in {"changes_requested", "rejected", "approved", "published", "suspended", "archived"}:
            existing = SkillHubService._load_reviewer_notes(submission.reviewer_notes_json)
            existing.append(notes)
            submission.reviewer_notes_json = json.dumps(existing)

        session.add(
            SkillHubTransition(
                submission_id=submission.id,
                from_state=from_state,
                to_state=next_state,
                actor_id=actor_id,
                actor_role=actor_role,
                notes=notes,
                created_at=SkillHubService.now(),
            )
        )

        if submission.skill_id:
            skill = await session.get(Skill, submission.skill_id)
            if skill is not None:
                skill.status = next_state
                skill.visibility = "public" if next_state == "published" else "private"

        return submission

    @staticmethod
    async def get_submission(session: AsyncSession, submission_id: str) -> SkillHubSubmission | None:
        """Fetch a submission by ID."""
        return await session.get(SkillHubSubmission, submission_id)

    @staticmethod
    async def list_history(session: AsyncSession, submission_id: str) -> list[SkillHubTransition]:
        """Fetch ordered transition history for a submission."""
        rows = await session.execute(
            select(SkillHubTransition)
            .where(SkillHubTransition.submission_id == submission_id)
            .order_by(SkillHubTransition.created_at.asc())
        )
        return rows.scalars().all()

    @staticmethod
    async def review_queue(
        session: AsyncSession,
        *,
        state: str | None,
        risk_label: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[SkillHubSubmission]:
        """List review queue rows with state/date/risk filtering."""
        clauses = []
        if state:
            clauses.append(SkillHubSubmission.current_state == state)
        if risk_label:
            clauses.append(SkillHubSubmission.risk_label == risk_label)
        if date_from:
            clauses.append(SkillHubSubmission.created_at >= date_from)
        if date_to:
            clauses.append(SkillHubSubmission.created_at <= date_to)

        query = select(SkillHubSubmission).order_by(SkillHubSubmission.updated_at.desc())
        if clauses:
            query = query.where(and_(*clauses))
        rows = await session.execute(query)
        return rows.scalars().all()

    @staticmethod
    def _load_reviewer_notes(raw: str | None) -> list[str]:
        """Safely decode reviewer notes JSON payload."""
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in payload if isinstance(item, str)]

    @staticmethod
    def serialize_submission(submission: SkillHubSubmission, history: list[SkillHubTransition]) -> dict[str, Any]:
        """Serialize ORM entities to API response payload."""
        return {
            "id": submission.id,
            "skill_id": submission.skill_id,
            "skill_slug": submission.skill_slug,
            "title": submission.title,
            "description": submission.description,
            "risk_label": submission.risk_label,
            "revision": submission.revision,
            "submitted_by": submission.submitted_by,
            "current_state": submission.current_state,
            "reviewer_notes": SkillHubService._load_reviewer_notes(submission.reviewer_notes_json),
            "created_at": submission.created_at,
            "updated_at": submission.updated_at,
            "history": [
                {
                    "id": event.id,
                    "from_state": event.from_state,
                    "to_state": event.to_state,
                    "actor_id": event.actor_id,
                    "actor_role": event.actor_role,
                    "notes": event.notes,
                    "created_at": event.created_at,
                }
                for event in history
            ],
        }
