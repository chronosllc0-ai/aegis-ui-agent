"""Database readiness regression tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend import database


def test_get_session_rejects_requests_until_database_is_ready(tmp_path: Path) -> None:
    """Request-scoped DB access should return a clean 503 while tables are still warming up."""
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / 'db_readiness.db'}")

    async def _run() -> None:
        with pytest.raises(HTTPException) as exc_info:
            async for _ in database.get_session():
                pass
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Database is still initializing"

        await database.create_tables()

        async for session in database.get_session():
            assert session is not None
            break

    asyncio.run(_run())
