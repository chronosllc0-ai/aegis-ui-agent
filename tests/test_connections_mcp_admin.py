"""Regression tests for MCP presets/custom servers and admin connection wizard endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database
from config import settings


def _init_test_db(tmp_path: Path) -> None:
    import backend.connections.models  # noqa: F401

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'connections.db'}"
    settings.DATABASE_URL = db_url
    database.init_db(db_url)
    asyncio.run(database.create_tables())


def _mock_verify_session(token: str | None):
    if token == 'admin-token':
        return {"uid": "admin-1", "email": "admin@example.com", "role": "admin", "status": "active"}
    if token == 'user-token':
        return {"uid": "user-1", "email": "user@example.com", "role": "user", "status": "active"}
    return None


def _seed_users() -> None:
    from backend.database import User
    from backend.connections.service import ensure_default_mcp_presets

    async def _run() -> None:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            session.add(User(uid='admin-1', provider='password', provider_id='admin-1', email='admin@example.com', name='Admin', role='admin', status='active'))
            session.add(User(uid='user-1', provider='password', provider_id='user-1', email='user@example.com', name='User', role='user', status='active'))
            await session.commit()
            await ensure_default_mcp_presets(session)

    asyncio.run(_run())


def test_preset_and_custom_mcp_flows(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    _seed_users()
    import main
    main.db_ready = True

    with patch('auth._verify_session', side_effect=_mock_verify_session), TestClient(main.app) as client:
        database._database_ready = True  # type: ignore[attr-defined]
        client.cookies.set('aegis_session', 'user-token')

        presets = client.get('/api/mcp/presets')
        assert presets.status_code == 200
        preset_id = presets.json()['presets'][0]['id']

        added = client.post('/api/mcp/servers/from-preset', json={'preset_id': preset_id})
        assert added.status_code == 200

        custom = client.post('/api/mcp/servers/custom', json={
            'name': 'My MCP',
            'server_url': 'http://localhost:3333/mcp',
            'auth_type': 'none',
        })
        assert custom.status_code == 200

        servers = client.get('/api/mcp/servers')
        assert servers.status_code == 200
        assert len(servers.json()['servers']) == 2


def test_admin_connection_creation_enforced_and_test_messages(tmp_path: Path) -> None:
    _init_test_db(tmp_path)
    _seed_users()
    import main
    main.db_ready = True

    with patch('auth._verify_session', side_effect=_mock_verify_session), TestClient(main.app) as client:
        database._database_ready = True  # type: ignore[attr-defined]
        client.cookies.set('aegis_session', 'user-token')
        denied = client.post('/api/admin/connections', json={
            'name': 'Nope',
            'connection_type': 'mcp',
            'config': {},
            'status': 'draft',
        })
        assert denied.status_code == 403

        client.cookies.set('aegis_session', 'admin-token')
        created = client.post('/api/admin/connections', json={
            'name': 'Admin MCP',
            'subtitle': 'sub',
            'description': 'desc',
            'logo_url': '',
            'connection_type': 'mcp',
            'config': {'transport': 'http', 'url': 'http://localhost:3333/mcp'},
            'status': 'published',
        })
        assert created.status_code == 200

        test_ok = client.post('/api/admin/connections/test', json={
            'connection_type': 'mcp',
            'config': {'transport': 'http', 'url': 'http://localhost:3333/mcp'},
        })
        assert test_ok.status_code == 200
        assert test_ok.json()['ok'] is True

        test_fail = client.post('/api/admin/connections/test', json={
            'connection_type': 'mcp',
            'config': {'transport': 'http', 'url': 'invalid-url'},
        })
        assert test_fail.status_code == 200
        assert test_fail.json()['ok'] is False
        assert 'valid http(s) URL' in test_fail.json()['message']

        oauth_fail = client.post('/api/admin/connections/test', json={
            'connection_type': 'oauth',
            'config': {'auth_url': 'banana', 'token_url': 'javascript:alert(1)'},
        })
        assert oauth_fail.status_code == 200
        assert oauth_fail.json()['ok'] is False
