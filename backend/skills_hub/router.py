"""API router for Skill Hub submission + review workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.admin.dependencies import get_admin_user
from backend.database import User, get_session
from backend.skills_hub.schemas import SkillHubSubmissionCreateRequest, SkillHubTransitionRequest
from backend.skills_hub.service import SkillHubService

skills_hub_router = APIRouter(prefix="/api/skills/hub", tags=["skills-hub"])


async def _get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or not payload.get("uid"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await session.get(User, payload["uid"])
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@skills_hub_router.post("/submissions")
async def create_submission(
    body: SkillHubSubmissionCreateRequest,
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        submission = await SkillHubService.create_submission(
            session,
            submitter_id=current_user.uid,
            skill_id=body.skill_id,
            skill_slug=body.skill_slug,
            title=body.title,
            description=body.description,
            risk_label=body.risk_label,
            previous_submission_id=body.previous_submission_id,
            submit_now=body.submit_now,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.commit()
    history = await SkillHubService.list_history(session, submission.id)
    return {"ok": True, "submission": SkillHubService.serialize_submission(submission, history)}


@skills_hub_router.get("/submissions/{submission_id}")
async def get_submission(
    submission_id: str,
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    submission = await SkillHubService.get_submission(session, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    if current_user.role not in {"admin", "superadmin"} and submission.submitted_by != current_user.uid:
        raise HTTPException(status_code=403, detail="Not authorized")

    history = await SkillHubService.list_history(session, submission.id)
    return {
        "ok": True,
        "submission": SkillHubService.serialize_submission(submission, history),
        "allowed_transitions": list(SkillHubService.allowed_transitions(submission.current_state)),
    }


@skills_hub_router.post("/submissions/{submission_id}/transition")
async def transition_submission(
    submission_id: str,
    body: SkillHubTransitionRequest,
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        submission = await SkillHubService.transition_submission(
            session,
            submission_id=submission_id,
            actor_id=current_user.uid,
            actor_role=current_user.role,
            next_state=body.next_state,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    await session.commit()
    history = await SkillHubService.list_history(session, submission.id)
    return {
        "ok": True,
        "submission": SkillHubService.serialize_submission(submission, history),
        "allowed_transitions": list(SkillHubService.allowed_transitions(submission.current_state)),
    }


@skills_hub_router.get("/review-queue")
async def get_review_queue(
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
    state: str | None = Query(default=None),
    risk_label: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> dict[str, Any]:
    _ = admin_user
    queue = await SkillHubService.review_queue(
        session,
        state=state,
        risk_label=risk_label,
        date_from=date_from,
        date_to=date_to,
    )
    return {
        "ok": True,
        "items": [
            {
                "id": item.id,
                "skill_slug": item.skill_slug,
                "title": item.title,
                "risk_label": item.risk_label,
                "current_state": item.current_state,
                "submitted_by": item.submitted_by,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "revision": item.revision,
            }
            for item in queue
        ],
    }
