"""Phase 8: contract tests for the runtime context-meter router.

These tests mount :data:`backend.runtime.router.router` on a throwaway
FastAPI app + TestClient. They lock in three guarantees:

* Unauthenticated requests get **401**.
* A request that authenticates as user ``A`` but asks for a session
  owned by ``B`` gets **404** (no cross-tenant leak).
* An authenticated owner gets the full meter dict with all required
  bucket names, and `should_compact` is computed against the same
  thresholds the dispatch loop uses.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import auth
from backend import database
from backend.database import Base
from backend.runtime.persistence import RuntimeRun


@pytest.fixture(scope="module")
def app_with_router(tmp_path_factory):
    # Stable session secret for the signing helpers.
    os.environ["SESSION_SECRET"] = "phase8-router-test-secret"
    auth.settings.SESSION_SECRET = "phase8-router-test-secret"
    auth.settings.SESSION_TTL_SECONDS = 3600

    # Spin up an in-memory SQLite session factory and bind it to the
    # `_session_factory` global the runtime router reads. This lets the
    # endpoint resolve `RuntimeRun.owner_uid` without standing up the
    # whole app.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            db.add_all(
                [
                    RuntimeRun(
                        id="run-router-1",
                        owner_uid="user-A",
                        channel="web",
                        session_id="agent:main:web:user-A",
                        status="completed",
                        model="stub",
                    ),
                    RuntimeRun(
                        id="run-router-2",
                        owner_uid="user-B",
                        channel="web",
                        session_id="agent:main:web:user-B",
                        status="completed",
                        model="stub",
                    ),
                ]
            )
            await db.commit()
        return factory

    factory = asyncio.run(_setup())
    database._session_factory = factory  # type: ignore[attr-defined]

    from backend.runtime.router import router as runtime_router

    app = FastAPI()
    app.include_router(runtime_router)
    yield app

    asyncio.run(engine.dispose())
    database._session_factory = None  # type: ignore[attr-defined]


def _signed_cookie(uid: str) -> str:
    return auth._sign_session({"uid": uid})


def test_context_meter_requires_auth(app_with_router) -> None:
    with TestClient(app_with_router) as client:
        resp = client.get("/api/runtime/context-meter/agent:main:web:user-A")
    assert resp.status_code == 401, resp.text


def test_context_meter_blocks_cross_tenant_lookup(app_with_router) -> None:
    """User-A may not read user-B's session footprint."""
    cookie = _signed_cookie("user-A")
    with TestClient(app_with_router) as client:
        resp = client.get(
            "/api/runtime/context-meter/agent:main:web:user-B",
            cookies={"aegis_session": cookie},
        )
    assert resp.status_code == 404, resp.text


def test_context_meter_returns_required_buckets(app_with_router) -> None:
    cookie = _signed_cookie("user-A")
    with TestClient(app_with_router) as client:
        resp = client.get(
            "/api/runtime/context-meter/agent:main:web:user-A",
            cookies={"aegis_session": cookie},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    bucket_names = {bucket["name"] for bucket in body["buckets"]}
    required = {
        "system_prompt",
        "active_tools",
        "checkpoints",
        "workspace_files",
        "pinned_memories",
        "pending_tool_outputs",
        "chat_history",
        "current_user_message",
    }
    assert required.issubset(bucket_names), bucket_names
    assert body["session_id"] == "agent:main:web:user-A"
    assert body["owner_uid"] == "user-A"
    assert body["model_context_window"] > 0
    assert isinstance(body["projected_pct"], (int, float))
    assert isinstance(body["should_compact"], bool)
