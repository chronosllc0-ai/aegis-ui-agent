"""API routes for secure user/admin skill ecosystem workflows."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.admin.dependencies import get_admin_user
from backend.database import Skill, SkillAuditEvent, User, get_session
from backend.skills.policy_store import get_blocklist_state, get_skills_policy, set_blocklist_state, set_skills_policy
from backend.skills.service import APPROVED_STATUSES, REVIEW_SLA_MESSAGE, SkillService

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


class SkillToggleRequest(BaseModel):
    """Toggle payload for compatibility endpoint."""

    skill_id: str = Field(min_length=1, max_length=255)
    enabled: bool


class AdminSkillPolicyRequest(BaseModel):
    """Organization-level skill policy payload."""

    allow_unreviewed_installs: bool = False
    block_high_risk_skills: bool = False
    require_approval_before_install: bool = False
    default_enabled_skill_ids: list[str] = Field(default_factory=list)


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
        "sla_message": REVIEW_SLA_MESSAGE if body.workflow_action == "submit_review" else None,
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
        await session.commit()
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


@skills_router.post("/api/skills/toggle")
async def toggle_installed_skill(
    body: SkillToggleRequest,
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        install = await SkillService.set_skill_enabled(
            session,
            user_id=current_user.uid,
            skill_id=body.skill_id,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return {"ok": True, "skill_id": install.skill_id, "enabled": install.enabled}


@skills_router.delete("/api/skills/{skill_id}")
async def uninstall_skill_delete(
    skill_id: str,
    current_user: User = Depends(_get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    removed = await SkillService.uninstall_skill(session, user_id=current_user.uid, skill_id=skill_id)
    await session.commit()
    return {"ok": True, "removed": removed}


@skills_router.get("/api/admin/skills/policy")
async def get_admin_skills_policy(
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _ = admin_user
    return {"ok": True, "policy": await get_skills_policy(session)}


@skills_router.post("/api/admin/skills/policy")
async def set_admin_skills_policy(
    body: AdminSkillPolicyRequest,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    policy = await set_skills_policy(
        session,
        policy={
            "allow_unreviewed_installs": body.allow_unreviewed_installs,
            "block_high_risk_skills": body.block_high_risk_skills,
            "require_approval_before_install": body.require_approval_before_install,
            "default_enabled_skill_ids": body.default_enabled_skill_ids,
        },
        admin_uid=admin_user.uid,
    )
    await session.commit()
    return {"ok": True, "policy": policy}


@skills_router.get("/api/admin/skills/allow-block")
async def list_allow_block(
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
    q: str | None = None,
) -> dict[str, Any]:
    _ = admin_user
    filters = [Skill.status.in_(APPROVED_STATUSES)]
    if q:
        search_value = f"%{q.strip()}%"
        filters.append((Skill.name.ilike(search_value)) | (Skill.slug.ilike(search_value)))

    rows = await session.execute(select(Skill).where(and_(*filters)).order_by(desc(Skill.updated_at)).limit(200))
    state_map = await get_blocklist_state(session)
    items: list[dict[str, Any]] = []
    for skill in rows.scalars().all():
        entry = state_map.get(skill.id, {})
        state = entry.get("state")
        items.append(
            {
                "skill_id": skill.id,
                "skill": skill.name,
                "slug": skill.slug,
                "version": skill.status,
                "risk": skill.risk_label or "unknown",
                "allowed": state == "allow",
                "blocked": state == "block",
                "updated": entry.get("updated_at") or skill.updated_at,
            }
        )
    return {"ok": True, "items": items}


async def _set_skill_override(*, session: AsyncSession, skill_id: str, state: str | None, admin_uid: str) -> None:
    state_map = await get_blocklist_state(session)
    now_iso = datetime.now(timezone.utc).isoformat()
    if state is None:
        state_map.pop(skill_id, None)
    else:
        state_map[skill_id] = {"state": state, "updated_at": now_iso, "updated_by": admin_uid}
    await set_blocklist_state(session, state=state_map, admin_uid=admin_uid)


@skills_router.post("/api/admin/skills/{skill_id}/allow")
async def allow_skill(
    skill_id: str,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _set_skill_override(session=session, skill_id=skill_id, state="allow", admin_uid=admin_user.uid)
    await session.commit()
    return {"ok": True}


@skills_router.post("/api/admin/skills/{skill_id}/block")
async def block_skill(
    skill_id: str,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _set_skill_override(session=session, skill_id=skill_id, state="block", admin_uid=admin_user.uid)
    await session.commit()
    return {"ok": True}


@skills_router.post("/api/admin/skills/{skill_id}/reset")
async def reset_skill_override(
    skill_id: str,
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _set_skill_override(session=session, skill_id=skill_id, state=None, admin_uid=admin_user.uid)
    await session.commit()
    return {"ok": True}


@skills_router.get("/api/admin/skills/install-audit")
async def list_install_audit(
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
    user: str | None = None,
    skill: str | None = None,
    action: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    _ = admin_user
    page = max(page, 1)
    page_size = max(1, min(page_size, 100))
    filters = [SkillAuditEvent.event_type.in_(["install", "install_blocked", "uninstall"])]
    if user:
        filters.append(SkillAuditEvent.actor_id == user)
    if skill:
        filters.append(SkillAuditEvent.skill_id == skill)
    if action:
        filters.append(SkillAuditEvent.event_type == action)
    if date_from:
        filters.append(SkillAuditEvent.created_at >= date_from)
    if date_to:
        filters.append(SkillAuditEvent.created_at <= date_to)

    total_result = await session.execute(select(func.count()).select_from(SkillAuditEvent).where(and_(*filters)))
    total = int(total_result.scalar() or 0)
    rows = await session.execute(
        select(SkillAuditEvent)
        .where(and_(*filters))
        .order_by(desc(SkillAuditEvent.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    entries = rows.scalars().all()
    return {
        "ok": True,
        "items": [
            {
                "id": entry.id,
                "user": entry.actor_id,
                "skill_id": entry.skill_id,
                "action": entry.event_type,
                "reason": entry.reason,
                "timestamp": entry.created_at,
            }
            for entry in entries
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@skills_router.get("/api/admin/skills/review-queue")
async def list_admin_review_queue(
    admin_user: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
    status: str | None = None,
) -> dict[str, Any]:
    _ = admin_user
    queue = await SkillService.get_review_queue(session)
    allowed_statuses = {"draft", "submitted", "scanning", "scan_failed", "review", "rejected", "published_global", "published_hub"}
    filtered = queue
    if status:
        if status not in allowed_statuses:
            raise HTTPException(status_code=400, detail="Unsupported status filter")
        filtered = [item for item in queue if item["submission"].review_state == status]
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
