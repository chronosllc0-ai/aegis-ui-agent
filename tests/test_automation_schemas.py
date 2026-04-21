"""Tests for automation execution target schema compatibility and normalization."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.automation import TaskCreate, TaskUpdate, _task_to_dict, _validate_target_update


class _TaskStub(SimpleNamespace):
    """ScheduledTask-like stub for schema helper tests."""


def test_task_create_defaults_to_assistant_prompt_and_accepts_legacy_prompt() -> None:
    body = TaskCreate(name="Daily", prompt="Summarize inbox", cron_expr="0 9 * * 1")

    assert body.execution_target_type == "assistant_prompt"
    assert body.assistant_task_prompt == "Summarize inbox"
    assert body.prompt == "Summarize inbox"
    assert body.workflow_id is None


def test_task_create_requires_workflow_id_for_saved_workflow() -> None:
    with pytest.raises(ValueError, match="workflow_id is required"):
        TaskCreate(
            name="Workflow",
            execution_target_type="saved_workflow",
            cron_expr="0 9 * * 1",
        )


def test_validate_target_update_enforces_prompt_for_assistant_prompt() -> None:
    task = _TaskStub(execution_target_type="assistant_prompt", prompt="", workflow_id=None)

    with pytest.raises(HTTPException) as exc:
        _validate_target_update(task, TaskUpdate(execution_target_type="assistant_prompt"))

    assert exc.value.status_code == 422


def test_task_to_dict_normalizes_new_and_legacy_fields() -> None:
    task = _TaskStub(
        id="task-1",
        user_id="u-1",
        name="Name",
        description=None,
        execution_target_type=None,
        workflow_id=None,
        prompt="Do work",
        cron_expr="0 9 * * 1",
        timezone="UTC",
        enabled=True,
        last_run_at=None,
        next_run_at=None,
        last_status="pending",
        last_error=None,
        run_count=0,
        created_at=None,
        updated_at=None,
    )

    payload = _task_to_dict(task)

    assert payload["execution_target_type"] == "assistant_prompt"
    assert payload["assistant_task_prompt"] == "Do work"
    assert payload["workflow_id"] is None
    assert payload["prompt"] == "Do work"
