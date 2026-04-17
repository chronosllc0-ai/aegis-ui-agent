"""API tests for workspace file visibility and admin mutation controls."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import database
from backend.admin.workspace_files import router as admin_workspace_files_router
from backend.database import User
from backend.workspace_files import workspace_files_router


def _init_test_db(tmp_path: Path) -> None:
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'workspace_files_api.db'}")
    asyncio.run(database.create_tables())


async def _seed_users() -> None:
    async with database._session_factory() as session:  # type: ignore[union-attr]
        session.add_all(
            [
                User(uid='admin-1', email='admin@example.com', role='admin', status='active'),
                User(uid='user-1', email='user@example.com', role='user', status='active'),
            ]
        )
        await session.commit()


def _mock_verify_session(token: str | None) -> dict[str, str] | None:
    if not token:
        return None
    return {'uid': token}


def test_user_can_read_workspace_files(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())

    app = FastAPI()
    app.include_router(workspace_files_router)

    with TestClient(app) as client, patch('auth._verify_session', side_effect=_mock_verify_session):
        client.cookies.set('aegis_session', 'user-1')
        response = client.get('/api/workspace-files')

    assert response.status_code == 200
    payload = response.json()
    assert len(payload['files']) == 7
    assert payload['files'][0]['name'] == 'AGENTS.md'


def test_non_admin_cannot_patch_workspace_files(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())

    app = FastAPI()
    app.include_router(admin_workspace_files_router, prefix='/api/admin')

    with TestClient(app) as client, patch('auth._verify_session', side_effect=_mock_verify_session):
        client.cookies.set('aegis_session', 'user-1')
        response = client.patch('/api/admin/workspace-files', json={'files': {'AGENTS.md': '# Updated'}})

    assert response.status_code == 403
    assert response.json()['detail'] == 'Admin access required'


def test_admin_can_patch_workspace_files(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())

    app = FastAPI()
    app.include_router(admin_workspace_files_router, prefix='/api/admin')

    with TestClient(app) as client, patch('auth._verify_session', side_effect=_mock_verify_session):
        client.cookies.set('aegis_session', 'admin-1')
        response = client.patch('/api/admin/workspace-files', json={'files': {'USER.md': '# Persona'}})

    assert response.status_code == 200
    payload = response.json()
    user_file = next(item for item in payload['files'] if item['name'] == 'USER.md')
    assert user_file['content'] == '# Persona'


def test_admin_patch_rejects_unknown_workspace_file_name(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    asyncio.run(_seed_users())

    app = FastAPI()
    app.include_router(admin_workspace_files_router, prefix='/api/admin')

    with TestClient(app) as client, patch('auth._verify_session', side_effect=_mock_verify_session):
        client.cookies.set('aegis_session', 'admin-1')
        response = client.patch('/api/admin/workspace-files', json={'files': {'PERSONALITY.md': '# Nope'}})

    assert response.status_code == 400
    assert 'Unsupported workspace files' in response.json()['detail']
