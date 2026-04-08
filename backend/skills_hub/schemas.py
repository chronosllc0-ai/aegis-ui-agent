"""Pydantic schemas for Skill Hub submission and review workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SkillHubState = Literal[
    "draft",
    "submitted",
    "under_review",
    "changes_requested",
    "approved",
    "published",
    "suspended",
    "archived",
    "rejected",
]


class SkillHubSubmissionCreateRequest(BaseModel):
    """Payload for creating a new Skill Hub submission revision."""

    skill_id: str | None = Field(default=None, max_length=255)
    skill_slug: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=4000)
    risk_label: str = Field(default="unknown", max_length=30)
    admin_override: bool = False
    previous_submission_id: str | None = Field(default=None, max_length=255)
    submit_now: bool = False


class SkillHubTransitionRequest(BaseModel):
    """Transition request payload with optional reviewer notes."""

    next_state: SkillHubState
    notes: str | None = Field(default=None, max_length=4000)


class SkillHubTransitionResponse(BaseModel):
    """Serialized transition history event."""

    id: str
    from_state: SkillHubState
    to_state: SkillHubState
    actor_id: str
    actor_role: str
    notes: str | None
    created_at: datetime


class SkillHubSubmissionResponse(BaseModel):
    """Submission details including state, notes, and transition history."""

    id: str
    skill_id: str | None
    skill_slug: str
    title: str
    description: str
    risk_label: str
    revision: int
    submitted_by: str
    current_state: SkillHubState
    reviewer_notes: list[str]
    created_at: datetime
    updated_at: datetime | None
    history: list[SkillHubTransitionResponse]
