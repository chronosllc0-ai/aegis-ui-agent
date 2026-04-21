"""API tests for automation job actions and run-history filtering."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import database
from backend.automation import _record_run, _run_history, automation_router
from backend.database import User


def _init_test_db(tmp_path: Path) -> None:
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'automation_endpoints.db'}")
    asyncio.run(database.create_tables())


async def _seed_user() -> None:
    async with database._session_factory() as session:  # type: ignore[union-attr]
        session.add(User(uid="user-1", email="user@example.com", role="user", status="active"))
        await session.commit()


def _mock_verify_session(token: str | None) -> dict[str, str] | None:
    if not token:
        return None
    return {"uid": token}


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(automation_router)
    return app


async def _noop_execute_task(task_id: str) -> None:  # pragma: no cover - scheduled side effect stub
    _ = task_id


def test_job_actions_clone_run_disable_remove(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_user())
    app = _build_app()

    with (
        TestClient(app) as client,
        patch("auth._verify_session", side_effect=_mock_verify_session),
        patch("backend.task_runner.execute_task", side_effect=_noop_execute_task),
    ):
        client.cookies.set("aegis_session", "user-1")

        create_response = client.post(
            "/api/automation/tasks",
            json={
                "name": "Daily sync",
                "execution_target_type": "assistant_prompt",
                "assistant_task_prompt": "Summarize pipeline status",
                "cron_expr": "0 9 * * 1",
            },
        )
        assert create_response.status_code == 200
        task_id = create_response.json()["task"]["id"]

        clone_response = client.post(f"/api/automation/tasks/{task_id}/clone")
        assert clone_response.status_code == 200
        assert clone_response.json()["ok"] is True
        assert clone_response.json()["task"]["name"] == "Daily sync (Copy)"

        run_response = client.post(f"/api/automation/tasks/{task_id}/run")
        assert run_response.status_code == 200
        assert run_response.json()["ok"] is True

        disable_response = client.patch(f"/api/automation/tasks/{task_id}", json={"enabled": False})
        assert disable_response.status_code == 200
        assert disable_response.json()["task"]["enabled"] is False

        remove_response = client.delete(f"/api/automation/tasks/{task_id}")
        assert remove_response.status_code == 200
        assert remove_response.json() == {"ok": True, "task_id": task_id, "removed": True}


def test_run_history_filters_by_status_scope_channel_and_date(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_user())
    app = _build_app()

    with TestClient(app) as client, patch("auth._verify_session", side_effect=_mock_verify_session):
        client.cookies.set("aegis_session", "user-1")

        create_response = client.post(
            "/api/automation/tasks",
            json={
                "name": "Filter test",
                "execution_target_type": "assistant_prompt",
                "assistant_task_prompt": "Ping",
                "cron_expr": "0 9 * * 1",
            },
        )
        assert create_response.status_code == 200
        task_id = create_response.json()["task"]["id"]

        _run_history.clear()
        _record_run(
            task_id,
            {
                "status": "success",
                "session_scope": "main",
                "delivery_channel": "chat",
                "started_at": datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc).isoformat(),
            },
        )
        _record_run(
            task_id,
            {
                "status": "failed",
                "session_scope": "isolated",
                "delivery_channel": "webhook",
                "started_at": datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc).isoformat(),
            },
        )

        filtered = client.get(
            f"/api/automation/tasks/{task_id}/runs",
            params={
                "status": "success",
                "scope": "main",
                "delivery_channel": " CHAT ",
                "date_from": "2026-04-19T00:00:00+00:00",
                "date_to": "2026-04-20T00:00:00+00:00",
            },
        )

    assert filtered.status_code == 200
    assert len(filtered.json()["runs"]) == 1
    assert filtered.json()["runs"][0]["status"] == "success"


def test_create_and_update_saved_workflow_validation_errors(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_user())

    with patch("backend.automation._compute_next_run", return_value=None):
        with patch("auth._verify_session", side_effect=_mock_verify_session):
            app = _build_app()
            with TestClient(app) as client:
                client.cookies.set("aegis_session", "user-1")
                create_invalid = client.post(
                    "/api/automation/tasks",
                    json={
                        "name": "Workflow",
                        "execution_target_type": "saved_workflow",
                        "cron_expr": "0 9 * * 1",
                    },
                )

                assert create_invalid.status_code == 422
                assert "workflow_id is required" in create_invalid.text
