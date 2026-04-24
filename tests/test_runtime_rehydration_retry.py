"""Codex PR #342 P1 regression test.

``_rehydrate_with_retry`` must poll for a usable session factory
before running the single rehydration pass. When the database layer
is still initialising, opening a session raises and the helper has to
back off + retry instead of declaring victory and leaving pending
rows stuck.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.runtime.integration as integration
from backend.database import Base
from backend.runtime.fanout import FanOutRegistry
from backend.runtime.persistence import RuntimeInboxEvent
from backend.runtime.supervisor import SupervisorRegistry


def _run(coro):
    return asyncio.run(coro)


def test_rehydration_retries_until_db_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        # Speed the retry loop up so the test takes ~0s, not ~60s.
        monkeypatch.setattr(integration, "_REHYDRATION_INTERVAL_SEC", 0.01)
        monkeypatch.setattr(integration, "_REHYDRATION_ATTEMPTS", 50)

        # Build the DB lazily so ``session_factory`` raises for the
        # first N calls and then starts returning real sessions.
        state: dict[str, object] = {"factory": None, "calls": 0}

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        real_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with real_factory() as db:
            db.add(
                RuntimeInboxEvent(
                    event_id="evt-retry",
                    owner_uid="retry-user",
                    channel="web",
                    session_id="agent:main:web:retry-user",
                    kind="chat_message",
                    priority=10,
                    payload=json.dumps({"text": "queued before db"}),
                    status="pending",
                    created_at=datetime.now(timezone.utc),
                    enqueued_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        def session_ctx():
            state["calls"] = int(state["calls"]) + 1  # type: ignore[arg-type]
            if int(state["calls"]) < 3:  # type: ignore[arg-type]
                raise RuntimeError("Database session factory is not initialised")
            return real_factory()

        enqueued: list[str] = []

        class _StubSupervisor:
            async def enqueue(self, event) -> None:
                enqueued.append(event.event_id)

        class _StubRegistry:
            async def get(self, owner_uid):  # noqa: D401 - test stub
                return _StubSupervisor()

            def set_persistence_factory(self, factory) -> None:  # noqa: D401
                return None

            async def shutdown(self) -> None:  # noqa: D401
                return None

        await integration._rehydrate_with_retry(  # type: ignore[attr-defined]
            registry=_StubRegistry(),  # type: ignore[arg-type]
            session_factory=session_ctx,  # type: ignore[arg-type]
            fanout_registry=FanOutRegistry(),
        )

        assert int(state["calls"]) >= 3, state  # type: ignore[arg-type]
        assert enqueued == ["evt-retry"], enqueued

        await engine.dispose()

    _run(scenario())
