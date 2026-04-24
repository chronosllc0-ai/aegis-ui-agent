"""Persistence layer for the always-on runtime.

Three concentric rings of durability:

* **runs** — one row per Agents SDK ``Runner.run`` invocation
  (``runtime_runs``).
* **run_events** — ordered log of the events emitted during a run
  (``runtime_run_events``).
* **inbox_events** — Phase 7: the supervisor's priority queue, persisted.
  Every :class:`~backend.runtime.events.AgentEvent` we accept via
  :meth:`SessionSupervisor.enqueue` gets a row with a status lifecycle
  (``pending`` → ``dispatched`` → ``completed`` / ``error`` /
  ``interrupted``). On boot the rehydration pass replays anything that
  was still ``pending`` and marks anything that was ``dispatched`` as
  ``interrupted`` so the fan-out can surface it to the UI.
* **tool_calls** — Phase 7: per-tool-call checkpoints scoped to a run.
  On restart, calls with no matching terminal row are marked
  ``interrupted``.

The tables live in the same ``Base`` as every other SQLAlchemy model, so
``Base.metadata.create_all`` (the test fixture path) creates them.
Production migrations use Alembic; when schema changes land here, an
accompanying revision must ship with them.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    and_,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Base
from backend.runtime.events import AgentEvent, EventKind, EventPriority

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


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


class RuntimeInboxEvent(Base):
    """Phase 7: persisted supervisor inbox entries.

    One row per :class:`AgentEvent` accepted by
    :meth:`SessionSupervisor.enqueue`. Serves two purposes:

    * **Rehydration** — on supervisor boot we re-enqueue rows still in
      ``pending`` and mark rows in ``dispatched`` as ``interrupted`` so
      the UI can show a clean "run interrupted, please retry" message.
    * **Post-mortem** — an audit trail of every event the agent saw.
    """

    __tablename__ = "runtime_inbox_events"

    event_id = Column(String(64), primary_key=True)
    owner_uid = Column(String(255), nullable=False, index=True)
    channel = Column(String(64), nullable=False)
    session_id = Column(String(255), nullable=False, index=True)
    kind = Column(String(64), nullable=False)
    priority = Column(Integer, nullable=False, default=int(EventPriority.BACKGROUND))
    payload = Column(Text, nullable=False, default="{}")
    reply_hint = Column(Text, nullable=True)
    correlation_id = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    enqueued_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    run_id = Column(String(64), nullable=True, index=True)
    error = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_runtime_inbox_owner_status", "owner_uid", "status"),
    )


class RuntimeToolCall(Base):
    """Phase 7: per-tool-call checkpoint rows.

    Rows are created when the dispatch loop observes a ``tool_call_item``
    and updated when the matching ``tool_call_output_item`` lands. Tool
    calls still in ``started`` after a restart are marked
    ``interrupted`` by :func:`mark_inbox_interrupted`.
    """

    __tablename__ = "runtime_tool_calls"

    id = Column(String(64), primary_key=True)
    run_id = Column(
        String(64), ForeignKey("runtime_runs.id", ondelete="CASCADE"), nullable=False
    )
    event_id = Column(String(64), nullable=True, index=True)
    call_id = Column(String(128), nullable=True, index=True)
    owner_uid = Column(String(255), nullable=True, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    tool_name = Column(String(128), nullable=False)
    arguments = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="started", index=True)
    started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    output_preview = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_runtime_tool_calls_run_status", "run_id", "status"),
    )


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------


def new_run_id() -> str:
    return f"run_{uuid4().hex[:24]}"


def new_event_id() -> str:
    return f"evt_{uuid4().hex[:24]}"


def new_tool_call_id() -> str:
    return f"tc_{uuid4().hex[:24]}"


# ---------------------------------------------------------------------------
# Run records
# ---------------------------------------------------------------------------


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
    result = await session.execute(
        select(RuntimeRunEvent)
        .where(RuntimeRunEvent.run_id == run_id)
        .order_by(RuntimeRunEvent.seq.asc())
    )
    return list(result.scalars())


# ---------------------------------------------------------------------------
# Inbox event records (Phase 7)
# ---------------------------------------------------------------------------


async def record_inbox_event(
    session: AsyncSession,
    event: AgentEvent,
    *,
    session_id: str,
) -> None:
    """Persist a newly enqueued :class:`AgentEvent`.

    Idempotent on ``event_id`` — if the row already exists (e.g. because
    rehydration re-enqueued it) this is a no-op.
    """
    existing = await session.get(RuntimeInboxEvent, event.event_id)
    if existing is not None:
        return
    row = RuntimeInboxEvent(
        event_id=event.event_id,
        owner_uid=event.owner_uid,
        channel=event.channel,
        session_id=session_id,
        kind=event.kind.value,
        priority=int(event.effective_priority()),
        payload=json.dumps(event.payload or {}, ensure_ascii=False, default=str),
        reply_hint=(
            json.dumps(event.reply_hint, ensure_ascii=False, default=str)
            if event.reply_hint
            else None
        ),
        correlation_id=event.correlation_id,
        status="pending",
        created_at=datetime.fromtimestamp(event.created_at, tz=timezone.utc),
    )
    session.add(row)
    await session.commit()


async def mark_inbox_dispatched(
    session: AsyncSession,
    *,
    event_id: str,
    run_id: str | None = None,
) -> None:
    row = await session.get(RuntimeInboxEvent, event_id)
    if row is None:
        return
    row.status = "dispatched"
    row.dispatched_at = datetime.now(timezone.utc)
    if run_id is not None:
        row.run_id = run_id
    await session.commit()


async def mark_inbox_completed(
    session: AsyncSession,
    *,
    event_id: str,
    status: str = "completed",
    error: str | None = None,
) -> None:
    row = await session.get(RuntimeInboxEvent, event_id)
    if row is None:
        return
    row.status = status
    row.completed_at = datetime.now(timezone.utc)
    if error:
        row.error = error
    await session.commit()


async def list_unterminated_inbox_events(
    session: AsyncSession,
) -> list[RuntimeInboxEvent]:
    """Return inbox rows that still need attention after a restart.

    Rows in ``pending`` or ``dispatched`` are unterminated; terminal
    statuses (``completed``, ``error``, ``interrupted``) are skipped.
    """
    stmt = (
        select(RuntimeInboxEvent)
        .where(RuntimeInboxEvent.status.in_(("pending", "dispatched")))
        .order_by(RuntimeInboxEvent.created_at.asc())
    )
    return list((await session.execute(stmt)).scalars())


async def mark_inbox_interrupted(
    session: AsyncSession,
    *,
    event_id: str,
    error: str = "Supervisor restarted mid-dispatch",
) -> None:
    """Terminate a single dispatched event as ``interrupted``.

    Also cascades to any tool-call rows for the linked run that are
    still marked ``started``.
    """
    row = await session.get(RuntimeInboxEvent, event_id)
    if row is None:
        return
    row.status = "interrupted"
    row.completed_at = datetime.now(timezone.utc)
    row.error = error
    if row.run_id:
        await session.execute(
            update(RuntimeToolCall)
            .where(
                and_(
                    RuntimeToolCall.run_id == row.run_id,
                    RuntimeToolCall.status == "started",
                )
            )
            .values(
                status="interrupted",
                completed_at=datetime.now(timezone.utc),
                error=error,
            )
        )
        run_row = await session.get(RuntimeRun, row.run_id)
        if run_row is not None and run_row.status == "running":
            run_row.status = "interrupted"
            run_row.ended_at = datetime.now(timezone.utc)
            run_row.error = error
    await session.commit()


# ---------------------------------------------------------------------------
# Tool call records (Phase 7)
# ---------------------------------------------------------------------------


async def record_tool_call_started(
    session: AsyncSession,
    *,
    run_id: str,
    event_id: str | None,
    owner_uid: str | None,
    session_id: str,
    tool_name: str,
    arguments: str | None,
    call_id: str | None = None,
) -> str:
    """Insert a ``started`` tool-call row and return its id.

    Idempotent on ``(run_id, call_id)`` when ``call_id`` is provided —
    returns the existing row's id instead of inserting a duplicate.
    This matters because the dispatch loop may re-summarize new items
    if it ever retries.
    """
    if call_id:
        stmt = (
            select(RuntimeToolCall)
            .where(
                and_(
                    RuntimeToolCall.run_id == run_id,
                    RuntimeToolCall.call_id == call_id,
                )
            )
            .limit(1)
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return str(existing.id)
    row_id = new_tool_call_id()
    row = RuntimeToolCall(
        id=row_id,
        run_id=run_id,
        event_id=event_id,
        call_id=call_id,
        owner_uid=owner_uid,
        session_id=session_id,
        tool_name=tool_name,
        arguments=arguments,
        status="started",
    )
    session.add(row)
    await session.commit()
    return row_id


async def record_tool_call_completed(
    session: AsyncSession,
    *,
    run_id: str,
    call_id: str | None,
    output_preview: str | None,
    status: str = "completed",
    error: str | None = None,
) -> None:
    """Terminate the matching ``started`` row for ``(run_id, call_id)``.

    When ``call_id`` is ``None`` we update the most recent still-running
    row for this ``run_id`` as a best-effort match.
    """
    if call_id:
        where_clause = and_(
            RuntimeToolCall.run_id == run_id,
            RuntimeToolCall.call_id == call_id,
            RuntimeToolCall.status == "started",
        )
    else:
        where_clause = and_(
            RuntimeToolCall.run_id == run_id,
            RuntimeToolCall.status == "started",
        )
    stmt = (
        select(RuntimeToolCall)
        .where(where_clause)
        .order_by(RuntimeToolCall.started_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return
    row.status = status
    row.completed_at = datetime.now(timezone.utc)
    if output_preview is not None:
        row.output_preview = output_preview[:4000]
    if error:
        row.error = error
    await session.commit()


# ---------------------------------------------------------------------------
# Rehydration helper: AgentEvent reconstruction
# ---------------------------------------------------------------------------


def rebuild_agent_event(row: RuntimeInboxEvent) -> AgentEvent:
    """Reconstruct an :class:`AgentEvent` from a persisted inbox row."""
    try:
        payload = json.loads(row.payload or "{}")
    except json.JSONDecodeError:
        payload = {}
    reply_hint: dict[str, Any] | None = None
    if row.reply_hint:
        try:
            reply_hint = json.loads(row.reply_hint)
        except json.JSONDecodeError:
            reply_hint = None
    return AgentEvent(
        owner_uid=row.owner_uid,
        channel=row.channel,
        kind=EventKind(row.kind),
        payload=payload,
        reply_hint=reply_hint,
        correlation_id=row.correlation_id,
        priority=EventPriority(int(row.priority)) if row.priority is not None else None,
        event_id=row.event_id,
        created_at=(
            row.created_at.timestamp()
            if isinstance(row.created_at, datetime)
            else float(row.created_at)
        ),
    )


__all__ = [
    # Models
    "RuntimeRun",
    "RuntimeRunEvent",
    "RuntimeInboxEvent",
    "RuntimeToolCall",
    # ID helpers
    "new_run_id",
    "new_event_id",
    "new_tool_call_id",
    # Run records
    "record_run_start",
    "record_run_end",
    "record_event",
    "list_events",
    # Inbox records
    "record_inbox_event",
    "mark_inbox_dispatched",
    "mark_inbox_completed",
    "mark_inbox_interrupted",
    "list_unterminated_inbox_events",
    # Tool call records
    "record_tool_call_started",
    "record_tool_call_completed",
    # Rehydration
    "rebuild_agent_event",
]
