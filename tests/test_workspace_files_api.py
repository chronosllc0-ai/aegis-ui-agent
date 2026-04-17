"""API tests for layered workspace files and RBAC controls."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend import database
from backend.admin.workspace_files import router as admin_workspace_files_router
from backend.database import User, WorkspaceFileAuditEvent
from backend.workspace_files import legacy_workspace_files_router, workspace_files_router


def _init_test_db(tmp_path: Path) -> None:
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'workspace_files_api.db'}")
    asyncio.run(database.create_tables())


async def _seed_users() -> None:
    async with database._session_factory() as session:  # type: ignore[union-attr]
        session.add_all(
            [
                User(uid="admin-1", email="admin@example.com", role="admin", status="active"),
                User(uid="user-1", email="user@example.com", role="user", status="active"),
                User(uid="user-2", email="user2@example.com", role="user", status="active"),
            ]
        )
        await session.commit()


def _mock_verify_session(token: str | None) -> dict[str, str] | None:
    if not token:
        return None
    return {"uid": token}


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(workspace_files_router)
    app.include_router(legacy_workspace_files_router)
    app.include_router(admin_workspace_files_router, prefix="/api/admin")
    return app


def test_user_scope_reads_effective_files_and_global_is_visible(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())
    app = _build_app()

    with TestClient(app) as client, patch("auth._verify_session", side_effect=_mock_verify_session):
        client.cookies.set("aegis_session", "user-1")
        user_scope = client.get("/api/workspace/files?scope=user")
        global_scope = client.get("/api/workspace/files?scope=global")

    assert user_scope.status_code == 200
    assert global_scope.status_code == 200
    assert len(user_scope.json()["files"]) == 7
    assert user_scope.json()["files"][0]["source"] == "global"
    assert global_scope.json()["files"][0]["name"] == "AGENTS.md"


def test_non_admin_cannot_write_global_scope(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())
    app = _build_app()

    with TestClient(app) as client, patch("auth._verify_session", side_effect=_mock_verify_session):
        client.cookies.set("aegis_session", "user-1")
        response = client.put("/api/workspace/files/AGENTS.md?scope=global", json={"content": "# Updated"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_admin_global_edit_propagates_unless_user_override_exists(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())
    app = _build_app()

    with TestClient(app) as client, patch("auth._verify_session", side_effect=_mock_verify_session):
        client.cookies.set("aegis_session", "user-1")
        local_write = client.put("/api/workspace/files/USER.md?scope=user", json={"content": "user-1 local"})
        assert local_write.status_code == 200

        client.cookies.set("aegis_session", "admin-1")
        global_write = client.put("/api/workspace/files/USER.md?scope=global", json={"content": "global value"})
        assert global_write.status_code == 200

        client.cookies.set("aegis_session", "user-1")
        user_1_read = client.get("/api/workspace/files?scope=user")
        client.cookies.set("aegis_session", "user-2")
        user_2_read = client.get("/api/workspace/files?scope=user")

    user_1_file = next(item for item in user_1_read.json()["files"] if item["name"] == "USER.md")
    user_2_file = next(item for item in user_2_read.json()["files"] if item["name"] == "USER.md")
    assert user_1_file["content"] == "user-1 local"
    assert user_1_file["source"] == "user"
    assert user_2_file["content"] == "global value"
    assert user_2_file["source"] == "global"


def test_delete_user_scope_reverts_to_global(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())
    app = _build_app()

    with TestClient(app) as client, patch("auth._verify_session", side_effect=_mock_verify_session):
        client.cookies.set("aegis_session", "admin-1")
        assert client.put("/api/workspace/files/TOOLS.md?scope=global", json={"content": "global tools"}).status_code == 200
        client.cookies.set("aegis_session", "user-1")
        assert client.put("/api/workspace/files/TOOLS.md?scope=user", json={"content": "user override"}).status_code == 200
        delete_response = client.delete("/api/workspace/files/TOOLS.md?scope=user")

    assert delete_response.status_code == 200
    assert delete_response.json()["file"]["content"] == "global tools"
    assert delete_response.json()["file"]["source"] == "global"


def test_audit_events_record_actor_file_and_diff_hash(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())
    app = _build_app()

    with TestClient(app) as client, patch("auth._verify_session", side_effect=_mock_verify_session):
        client.cookies.set("aegis_session", "user-1")
        assert client.put("/api/workspace/files/MEMORY.md?scope=user", json={"content": "v1"}).status_code == 200
        assert client.put("/api/workspace/files/MEMORY.md?scope=user", json={"content": "v2"}).status_code == 200
        assert client.delete("/api/workspace/files/MEMORY.md?scope=user").status_code == 200

    async def _read_audit() -> list[WorkspaceFileAuditEvent]:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            return list((await session.execute(select(WorkspaceFileAuditEvent))).scalars())

    events = asyncio.run(_read_audit())
    assert len(events) == 3
    assert all(event.actor_id == "user-1" for event in events)
    assert all(event.file_name == "MEMORY.md" for event in events)
    assert all(len(event.diff_hash) == 64 for event in events)
