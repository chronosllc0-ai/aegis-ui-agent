"""API routes for admin and user skill catalog flows."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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


class SkillUploadRequest(BaseModel):
    """Admin skill upload payload."""

    slug: str = Field(min_length=3, max_length=120)
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    skill_md: str = Field(min_length=1)


class SkillReviewDecisionRequest(BaseModel):
    """Admin moderation decision payload."""

    decision: str = Field(pattern="^(approve_internal|approve_marketplace|reject|needs_changes)$")
    notes: str | None = Field(default=None, max_length=4000)


async def _get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    """Return authenticated current user."""
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or not payload.get("uid"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await session.get(User, payload["uid"])
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@skills_router.post("/api/admin/skills")
async def create_admin_skill(
    body: SkillUploadRequest,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a new skill + immutable version via admin flow."""
    try:
        skill = await SkillService.create_skill_with_version(
            session,
            slug=body.slug,
            name=body.name,
            description=body.description,
            owner_user_id=admin_user.uid,
            owner_type="admin",
            metadata_json=body.metadata_json,
            skill_markdown=body.skill_md,
            submitted_by=admin_user.uid,
            status="pending_scan",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.commit()
    return {"ok": True, "skill": {"id": skill.id, "slug": skill.slug, "status": skill.status}}


@skills_router.post("/api/admin/skills/{skill_id}/scan")
async def scan_admin_skill(
    skill_id: str,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Run VT + policy scans for a skill's latest version."""
    try:
        result = await SkillService.run_scans_for_skill(
            session,
            skill_id=skill_id,
            actor_id=admin_user.uid,
            actor_type="admin",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await session.commit()
    return {"ok": True, **result}


@skills_router.get("/api/admin/skills/review-queue")
async def list_admin_review_queue(
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List queued skills awaiting admin moderation."""
    _ = admin_user
    queue = await SkillService.get_review_queue(session)
    return {
        "ok": True,
        "items": [
            {
                "skill": {
                    "id": item["skill"].id,
                    "slug": item["skill"].slug,
                    "name": item["skill"].name,
                    "description": item["skill"].description,
                    "status": item["skill"].status,
                    "risk_label": item["skill"].risk_label,
                },
                "version": {
                    "id": item["version"].id,
                    "version": item["version"].version,
                    "content_sha256": item["version"].content_sha256,
                    "metadata_json": _safe_json_loads(item["version"].metadata_json),
                },
                "scans": [
                    {
                        "engine": scan.engine,
                        "verdict": scan.verdict,
                        "score": scan.score,
                        "report_url": scan.report_url,
                        "raw_json": _safe_json_loads(scan.raw_json),
                        "scanned_at": scan.scanned_at,
                    }
                    for scan in item["scans"]
                ],
            }
            for item in queue
        ],
    }


@skills_router.post("/api/admin/skills/{skill_id}/review")
async def review_admin_skill(
    skill_id: str,
    body: SkillReviewDecisionRequest,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Apply moderation decision (global vs hub approval, reject, or needs changes)."""
    try:
        skill = await SkillService.apply_review_decision(
            session,
            skill_id=skill_id,
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
            "visibility": skill.visibility,
            "is_new": skill.is_new,
            "new_until": skill.new_until,
        },
        "cta": {
            "approve_to_global": "approve_internal",
            "approve_to_hub": "approve_marketplace",
        },
    }


@skills_router.get("/api/skills/global")
async def list_global_skills(
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List skills approved for global/settings catalog visibility."""
    _ = current_user
    return {"ok": True, "skills": await SkillService.list_visibility(session, visibility="global")}


@skills_router.get("/api/skills/hub")
async def list_hub_skills(
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List skills approved for marketplace hub visibility."""
    _ = current_user
    return {"ok": True, "skills": await SkillService.list_visibility(session, visibility="hub")}


@skills_router.post("/api/skills/submit")
async def submit_user_skill(
    body: SkillUploadRequest,
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a community submission and move it into pending scan."""
    try:
        skill = await SkillService.create_skill_with_version(
            session,
            slug=body.slug,
            name=body.name,
            description=body.description,
            owner_user_id=current_user.uid,
            owner_type="user",
            metadata_json=body.metadata_json,
            skill_markdown=body.skill_md,
            submitted_by=current_user.uid,
            status="pending_scan",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.commit()
    scan_status = "completed"
    try:
        await SkillService.run_scans_for_skill(
            session,
            skill_id=skill.id,
            actor_id=current_user.uid,
            actor_type="user",
        )
        await session.commit()
    except ValueError as exc:
        logger.warning("Scan phase failed for skill %s: %s", skill.id, exc)
        await session.rollback()
        scan_status = "failed"
        await session.rollback()
        scan_status = "failed"

    return {
        "ok": True,
        "skill": {"id": skill.id, "slug": skill.slug, "status": skill.status},
        "scan_status": scan_status,
    }


@skills_router.get("/api/skills/mine")
async def list_my_skills(
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List all skills submitted by the authenticated user."""
    skills = await SkillService.list_user_skills(session, user_id=current_user.uid)
    return {
        "ok": True,
        "skills": [
            {
                "id": skill.id,
                "slug": skill.slug,
                "name": skill.name,
                "status": skill.status,
                "visibility": skill.visibility,
                "risk_label": skill.risk_label,
                "is_new": skill.is_new,
                "new_until": skill.new_until,
                "updated_at": skill.updated_at,
            }
            for skill in skills
        ],
    }


@skills_router.get("/api/skills/active")
async def list_active_skills(
    user_id: str = Query(..., min_length=1),
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List runtime-loadable skills after approval+scan compliance checks."""
    if current_user.uid != user_id and current_user.role not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Not authorized for requested user_id")

    skills = await SkillService.list_active_skills(session, requested_for_user_id=user_id)
    return {"ok": True, "skills": skills}
