"""API routes for secure user/admin skill ecosystem workflows."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.admin.dependencies import get_admin_user
from backend.database import User, get_session
from backend.skills.service import SkillService

skills_router = APIRouter(tags=["skills"])


def _safe_json_loads(text: str | None, *, default: dict[str, Any] | list[Any] | None = None) -> Any:
    """Safely parse stored JSON fields without failing endpoint responses."""
    fallback = {} if default is None else default
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


class SkillSubmitRequest(BaseModel):
    """Skill submission payload for admins or users."""

    slug: str = Field(min_length=3, max_length=120)
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    publish_target: str = Field(default="hub", pattern="^(global|hub)$")
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    skill_md: str = Field(min_length=1)
    workflow_action: str = Field(default="submit_review", pattern="^(save_draft|submit_review)$")


class SkillReviewDecisionRequest(BaseModel):
    """Admin moderation decision payload."""

    decision: str = Field(pattern="^(approve_global|approve_hub|reject|needs_changes)$")
    notes: str | None = Field(default=None, max_length=4000)


class SkillEnableRequest(BaseModel):
    """Enable/disable installed skill for runtime loading."""

    enabled: bool


async def _get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or not payload.get("uid"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await session.get(User, payload["uid"])
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@skills_router.get("/api/skills/hub")
async def list_hub_skills(
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _ = current_user
    return {"ok": True, "skills": await SkillService.list_catalog(session, publish_target="hub")}


@skills_router.post("/api/skills/submit")
async def submit_user_skill(
    body: SkillSubmitRequest,
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        publish_target = body.publish_target if current_user.role in {"admin", "superadmin"} else "hub"
        owner_type = "admin" if current_user.role in {"admin", "superadmin"} else "user"
        if body.workflow_action == "save_draft":
            skill, submission = await SkillService.save_draft(
                session,
                slug=body.slug,
                name=body.name,
                description=body.description,
                owner_user_id=current_user.uid,
                owner_type=owner_type,
                publish_target=publish_target,
                metadata_json=body.metadata_json,
                skill_markdown=body.skill_md,
                submitted_by=current_user.uid,
            )
        else:
            skill, submission = await SkillService.submit_skill(
                session,
                slug=body.slug,
                name=body.name,
                description=body.description,
                owner_user_id=current_user.uid,
                owner_type=owner_type,
                publish_target=publish_target,
                metadata_json=body.metadata_json,
                skill_markdown=body.skill_md,
                submitted_by=current_user.uid,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.commit()
    return {
        "ok": True,
        "workflow_action": body.workflow_action,
        "sla_message": "Review SLA: up to 5 working days." if body.workflow_action == "submit_review" else None,
        "skill": {"id": skill.id, "slug": skill.slug, "status": skill.status},
        "submission": {"id": submission.id, "review_state": submission.review_state},
    }


@skills_router.post("/api/skills/{skill_id}/install")
async def install_skill(
    skill_id: str,
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        install = await SkillService.install_skill(session, user_id=current_user.uid, skill_id=skill_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return {"ok": True, "skill_id": install.skill_id, "version_id": install.skill_version_id, "enabled": install.enabled}


@skills_router.post("/api/skills/{skill_id}/uninstall")
async def uninstall_skill(
    skill_id: str,
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    removed = await SkillService.uninstall_skill(session, user_id=current_user.uid, skill_id=skill_id)
    await session.commit()
    return {"ok": True, "removed": removed}


@skills_router.patch("/api/skills/{skill_id}/enable")
async def set_skill_enabled(
    skill_id: str,
    body: SkillEnableRequest,
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        install = await SkillService.set_skill_enabled(session, user_id=current_user.uid, skill_id=skill_id, enabled=body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return {"ok": True, "skill_id": install.skill_id, "enabled": install.enabled}


@skills_router.get("/api/skills/installed")
async def list_installed_skills(
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return {"ok": True, "skills": await SkillService.list_installed_skills(session, user_id=current_user.uid)}


@skills_router.get("/api/admin/skills/review-queue")
async def list_admin_review_queue(
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
    status: str | None = None,
) -> dict[str, Any]:
    _ = admin_user
    queue = await SkillService.get_review_queue(session)
    allowed_statuses = {"draft", "submitted", "scanning", "review", "approved", "rejected", "published_global", "published_hub"}
    filtered = queue
    if status:
        if status not in allowed_statuses:
            raise HTTPException(status_code=400, detail="Unsupported status filter")
        filtered = [item for item in queue if item["submission"].review_state == status or item["skill"].status == status]
    return {
        "ok": True,
        "statuses": sorted(allowed_statuses),
        "items": [
            {
                "submission": {
                    "id": item["submission"].id,
                    "skill_id": item["submission"].skill_id,
                    "version_id": item["submission"].version_id,
                    "submission_type": item["submission"].submission_type,
                    "review_state": item["submission"].review_state,
                    "created_at": item["submission"].created_at,
                },
                "skill": {
                    "id": item["skill"].id,
                    "slug": item["skill"].slug,
                    "name": item["skill"].name,
                    "status": item["skill"].status,
                    "publish_target": item["skill"].publish_target,
                    "risk_label": item["skill"].risk_label,
                },
                "version": {
                    "id": item["version"].id,
                    "version": item["version"].version,
                    "content_sha256": item["version"].content_sha256,
                    "storage_path": item["version"].storage_path,
                    "metadata_json": _safe_json_loads(item["version"].metadata_json),
                },
                "scans": [
                    {
                        "engine": scan.engine,
                        "verdict": scan.verdict,
                        "risk_label": scan.risk_label,
                        "report_url": scan.report_url,
                        "raw_json": _safe_json_loads(scan.raw_json),
                        "scanned_at": scan.scanned_at,
                    }
                    for scan in item["scans"]
                ],
            }
            for item in filtered
        ],
    }


@skills_router.post("/api/admin/skills/{submission_id}/scan")
async def scan_submission(
    submission_id: str,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        result = await SkillService.run_scans_for_submission(
            session,
            submission_id=submission_id,
            actor_id=admin_user.uid,
            actor_type="admin",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await session.commit()
    return {"ok": True, **result}


@skills_router.post("/api/admin/skills/{submission_id}/review")
async def review_submission(
    submission_id: str,
    body: SkillReviewDecisionRequest,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        skill = await SkillService.apply_review_decision(
            session,
            submission_id=submission_id,
            reviewer_admin_id=admin_user.uid,
            decision=body.decision,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.commit()
    return {
        "ok": True,
        "skill": {
            "id": skill.id,
            "status": skill.status,
            "publish_target": skill.publish_target,
            "is_new": skill.is_new,
            "new_until": skill.new_until,
        },
    }


@skills_router.get("/api/admin/skills/{skill_id}/history")
async def get_skill_history(
    skill_id: str,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _ = admin_user
    events = await SkillService.list_skill_history(session, skill_id=skill_id)
    return {
        "ok": True,
        "events": [
            {
                "id": event.id,
                "submission_id": event.submission_id,
                "version_id": event.skill_version_id,
                "event_type": event.event_type,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "actor_id": event.actor_id,
                "actor_type": event.actor_type,
                "reason": event.reason,
                "created_at": event.created_at,
            }
            for event in events
        ],
    }
