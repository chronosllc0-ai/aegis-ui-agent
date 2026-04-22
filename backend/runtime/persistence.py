"""Minimal persistence layer for the always-on runtime.

Phase 2 only needs enough persistence to prove the loop end-to-end:

* **runs** — one row per Agents SDK ``Runner.run_streamed`` invocation.
* **run_events** — ordered log of the events emitted during a run
  (user message, model message, tool call, tool result, final message).

Phases 3-5 will grow this into a fuller event / tool-call ledger. The
schema here is intentionally narrow so it's cheap to replay and easy to
migrate forward.

The tables live in the same ``Base`` as every other SQLAlchemy model, so
``Base.metadata.create_all`` (the test fixture path) creates them. A
proper Alembic migration lands with the rest of the Phase 2+ schema
work.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Base

logger = logging.getLogger(__name__)


class RuntimeRun(Base):
    """One Agents SDK run invocation."""

    __tablename__ = "runtime_runs"

    id = Column(String(64), primary_key=True)
    owner_uid = Column(String(255), nullable=True, index=True)
    channel = Column(String(64), nullable=False, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="running")
    model = Column(String(128), nullable=True)
    started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    ended_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)


class RuntimeRunEvent(Base):
    """Ordered event log for a run."""

    __tablename__ = "runtime_run_events"

    id = Column(String(64), primary_key=True)
    run_id = Column(
        String(64), ForeignKey("runtime_runs.id", ondelete="CASCADE"), nullable=False
    )
    seq = Column(Integer, nullable=False)
    kind = Column(String(64), nullable=False)
    payload = Column(Text, nullable=False, default="{}")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_runtime_run_events_run_seq", "run_id", "seq"),
    )


def new_run_id() -> str:
    return f"run_{uuid4().hex[:24]}"


def new_event_id() -> str:
    return f"evt_{uuid4().hex[:24]}"


async def record_run_start(
    session: AsyncSession,
    *,
    run_id: str,
    owner_uid: str | None,
    channel: str,
    session_id: str,
    model: str | None,
) -> None:
    run = RuntimeRun(
        id=run_id,
        owner_uid=owner_uid,
        channel=channel,
        session_id=session_id,
        status="running",
        model=model,
    )
    session.add(run)
    await session.commit()


async def record_run_end(
    session: AsyncSession,
    *,
    run_id: str,
    status: str,
    error: str | None = None,
) -> None:
    run = await session.get(RuntimeRun, run_id)
    if run is None:
        logger.warning("record_run_end: run_id=%s not found", run_id)
        return
    run.status = status
    run.ended_at = datetime.now(timezone.utc)
    if error:
        run.error = error
    await session.commit()


async def record_event(
    session: AsyncSession,
    *,
    run_id: str,
    seq: int,
    kind: str,
    payload: dict[str, Any],
) -> None:
    event = RuntimeRunEvent(
        id=new_event_id(),
        run_id=run_id,
        seq=seq,
        kind=kind,
        payload=json.dumps(payload, ensure_ascii=False, default=str),
    )
    session.add(event)
    await session.commit()


async def list_events(session: AsyncSession, *, run_id: str) -> list[RuntimeRunEvent]:
    from sqlalchemy import select

    result = await session.execute(
        select(RuntimeRunEvent)
        .where(RuntimeRunEvent.run_id == run_id)
        .order_by(RuntimeRunEvent.seq.asc())
    )
    return list(result.scalars())


__all__ = [
    "RuntimeRun",
    "RuntimeRunEvent",
    "new_run_id",
    "new_event_id",
    "record_run_start",
    "record_run_end",
    "record_event",
    "list_events",
]
