"""Context-window accounting and compaction checkpoints for the runtime.

The always-on runtime must never surprise a user with a compaction that
was not reflected in the UI meter. This module owns the server-side
projection used by both the dispatch loop and the diagnostic endpoint:
it accounts for the system prompt, active tool catalog, loaded session
history, pending tool output, memories/checkpoints, and the current
incoming message before a run is sent to the model.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence
from uuid import uuid4

from sqlalchemy import Column, DateTime, Integer, String, Text, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Base
from backend.runtime.persistence import RuntimeRun, RuntimeRunEvent, RuntimeToolCall

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
DEFAULT_CONTEXT_WINDOW_TOKENS = 128_000
DEFAULT_COMPACT_THRESHOLD_PCT = 90
DEFAULT_RECENT_EVENT_LIMIT = 48
DEFAULT_PENDING_TOOL_LIMIT = 8


class RuntimeContextCheckpoint(Base):
    """A compacted summary of previous loaded context for one session."""

    __tablename__ = "runtime_context_checkpoints"

    id = Column(String(64), primary_key=True)
    owner_uid = Column(String(255), nullable=False, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    source_event_count = Column(Integer, nullable=False, default=0)
    token_count = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


@dataclass(frozen=True)
class ContextBucket:
    name: str
    tokens: int
    chars: int
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tokens": self.tokens,
            "chars": self.chars,
            "description": self.description,
        }


@dataclass(frozen=True)
class PreparedContext:
    prompt: str
    meter: dict[str, Any]
    history_text: str
    latest_checkpoint: RuntimeContextCheckpoint | None
    recent_event_count: int


def runtime_context_window_tokens() -> int:
    raw = os.getenv("RUNTIME_CONTEXT_WINDOW_TOKENS")
    if not raw:
        return DEFAULT_CONTEXT_WINDOW_TOKENS
    try:
        return max(1_000, int(raw))
    except ValueError:
        return DEFAULT_CONTEXT_WINDOW_TOKENS


def runtime_compact_threshold_pct() -> int:
    raw = os.getenv("COMPACT_THRESHOLD_PCT")
    if not raw:
        return DEFAULT_COMPACT_THRESHOLD_PCT
    try:
        return min(99, max(50, int(raw)))
    except ValueError:
        return DEFAULT_COMPACT_THRESHOLD_PCT


def estimate_tokens(text: str | None) -> int:
    """Cheap deterministic token estimate."""
    if not text:
        return 0
    lexical = len(_TOKEN_RE.findall(text))
    by_chars = math.ceil(len(text) / 4)
    return max(1, max(by_chars, lexical))


def _bucket(name: str, text: str, description: str) -> ContextBucket:
    return ContextBucket(name=name, tokens=estimate_tokens(text), chars=len(text), description=description)


def _jsonish(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(value)


def _event_line(event: RuntimeRunEvent) -> str:
    try:
        payload = json.loads(event.payload or "{}")
    except json.JSONDecodeError:
        payload = {"raw": event.payload}
    text = payload.get("text") or payload.get("message") or payload.get("output")
    if text is None:
        text = payload
    return f"[{event.kind}] {_jsonish(text)[:1600]}"


async def _latest_checkpoint(session: AsyncSession, *, session_id: str) -> RuntimeContextCheckpoint | None:
    stmt = (
        select(RuntimeContextCheckpoint)
        .where(RuntimeContextCheckpoint.session_id == session_id)
        .order_by(RuntimeContextCheckpoint.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _recent_events(session: AsyncSession, *, session_id: str, limit: int) -> list[RuntimeRunEvent]:
    stmt = (
        select(RuntimeRunEvent)
        .join(RuntimeRun, RuntimeRun.id == RuntimeRunEvent.run_id)
        .where(RuntimeRun.session_id == session_id)
        .order_by(RuntimeRunEvent.created_at.desc(), RuntimeRunEvent.seq.desc())
        .limit(max(1, limit))
    )
    rows = list((await session.execute(stmt)).scalars())
    rows.reverse()
    return rows


async def _pending_tools(session: AsyncSession, *, session_id: str, limit: int) -> list[RuntimeToolCall]:
    stmt = (
        select(RuntimeToolCall)
        .where(and_(RuntimeToolCall.session_id == session_id, RuntimeToolCall.status == "started"))
        .order_by(RuntimeToolCall.started_at.desc())
        .limit(max(1, limit))
    )
    return list((await session.execute(stmt)).scalars())


def _tool_catalog_text(tool_names: Sequence[str]) -> str:
    clean = sorted({name for name in tool_names if name})
    if not clean:
        return ""
    return "\n".join(f"- {name}" for name in clean)


def _pending_tool_text(tools: Iterable[RuntimeToolCall]) -> str:
    lines: list[str] = []
    for call in tools:
        args = (call.arguments or "")[:800]
        lines.append(f"- {call.tool_name} status={call.status} args={args}")
    return "\n".join(lines)


def _prompt_from_parts(*, instructions: str, checkpoint_text: str, history_text: str, pending_tools_text: str, current_text: str) -> str:
    sections = [instructions.strip()]
    if checkpoint_text.strip():
        sections.append("Previous compacted checkpoint:\n" + checkpoint_text.strip())
    if history_text.strip():
        sections.append("Recent session history:\n" + history_text.strip())
    if pending_tools_text.strip():
        sections.append("Pending tool context:\n" + pending_tools_text.strip())
    sections.append("Current user message:\n" + current_text.strip())
    return "\n\n".join(section for section in sections if section)


async def build_prepared_context(
    *,
    session_factory: Any,
    session_id: str,
    owner_uid: str,
    current_text: str,
    instructions: str,
    tool_names: Sequence[str],
    model_context_window: int | None = None,
    threshold_pct: int | None = None,
    recent_event_limit: int = DEFAULT_RECENT_EVENT_LIMIT,
    pending_tool_limit: int = DEFAULT_PENDING_TOOL_LIMIT,
) -> PreparedContext:
    """Build the prompt input and truthful context meter for a run."""
    model_window = model_context_window or runtime_context_window_tokens()
    threshold = threshold_pct or runtime_compact_threshold_pct()
    checkpoint: RuntimeContextCheckpoint | None = None
    recent: list[RuntimeRunEvent] = []
    pending_tools: list[RuntimeToolCall] = []

    if session_factory is not None:
        try:
            async with session_factory() as db:
                checkpoint = await _latest_checkpoint(db, session_id=session_id)
                recent = await _recent_events(db, session_id=session_id, limit=recent_event_limit)
                pending_tools = await _pending_tools(db, session_id=session_id, limit=pending_tool_limit)
        except Exception:  # noqa: BLE001
            checkpoint = None
            recent = []
            pending_tools = []

    checkpoint_text = checkpoint.summary if checkpoint is not None else ""
    history_text = "\n".join(_event_line(event) for event in recent)
    pending_tools_text = _pending_tool_text(pending_tools)
    tool_catalog = _tool_catalog_text(tool_names)
    buckets = [
        _bucket("system_prompt", instructions, "Agent identity, behavior rules, and runtime guardrails."),
        _bucket("active_tools", tool_catalog, "Names of native, MCP, and connector tools loaded for this turn."),
        _bucket("checkpoints", checkpoint_text, "Latest compacted session checkpoint injected into the prompt."),
        _bucket("workspace_files", "", "Workspace file payloads loaded into the next prompt; zero until read-file tracking is active."),
        _bucket("pinned_memories", "", "Pinned memories and connector state injected into the next prompt."),
        _bucket("pending_tool_outputs", pending_tools_text, "Started tool calls and scratch output still relevant to the run."),
        _bucket("chat_history", history_text, "Recent persisted runtime event history loaded for continuity."),
        _bucket("current_user_message", current_text, "The incoming event prompt."),
    ]
    total = sum(bucket.tokens for bucket in buckets)
    pct = round((total / model_window) * 100, 2) if model_window else 0.0
    meter = {
        "session_id": session_id,
        "owner_uid": owner_uid,
        "model_context_window": model_window,
        "compact_threshold_pct": threshold,
        "total_tokens": total,
        "projected_pct": pct,
        "should_compact": pct >= threshold,
        "buckets": [bucket.as_dict() for bucket in buckets],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    prompt = _prompt_from_parts(
        instructions=instructions,
        checkpoint_text=checkpoint_text,
        history_text=history_text,
        pending_tools_text=pending_tools_text,
        current_text=current_text,
    )
    return PreparedContext(prompt=prompt, meter=meter, history_text=history_text, latest_checkpoint=checkpoint, recent_event_count=len(recent))


def _checkpoint_summary(previous: str, history: str, max_chars: int = 12_000) -> str:
    body = "\n\n".join(part for part in (previous.strip(), history.strip()) if part)
    if not body:
        body = "No prior session history was available when compaction was triggered."
    if len(body) > max_chars:
        body = body[-max_chars:]
    return (
        "CHECKPOINT: Runtime context was compacted proactively before the model window overflowed.\n"
        "Keep decisions, user intent, unresolved work, important tool results, and safety constraints.\n\n"
        + body
    )


async def maybe_create_checkpoint(*, session_factory: Any, prepared: PreparedContext, owner_uid: str, session_id: str) -> dict[str, Any] | None:
    """Persist a compaction checkpoint when the meter crosses threshold."""
    if not prepared.meter.get("should_compact") or session_factory is None:
        return None
    previous = prepared.latest_checkpoint.summary if prepared.latest_checkpoint is not None else ""
    summary = _checkpoint_summary(previous, prepared.history_text)
    row = RuntimeContextCheckpoint(
        id=f"ctx_{uuid4().hex[:24]}",
        owner_uid=owner_uid,
        session_id=session_id,
        summary=summary,
        source_event_count=prepared.recent_event_count,
        token_count=estimate_tokens(summary),
    )
    async with session_factory() as db:
        db.add(row)
        await db.commit()
    return {
        "checkpoint_id": row.id,
        "session_id": session_id,
        "owner_uid": owner_uid,
        "summary": summary,
        "source_event_count": row.source_event_count,
        "token_count": row.token_count,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


__all__ = [
    "ContextBucket",
    "PreparedContext",
    "RuntimeContextCheckpoint",
    "build_prepared_context",
    "estimate_tokens",
    "maybe_create_checkpoint",
    "runtime_compact_threshold_pct",
    "runtime_context_window_tokens",
]
