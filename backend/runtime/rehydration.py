"""Phase 7: supervisor boot rehydration.

On startup every :class:`SupervisorRegistry` rebuilds its inbox from
the ``runtime_inbox_events`` table. The pass is a single sweep:

* Rows in ``dispatched`` were in-flight when the process died. We
  terminate them as ``interrupted`` and publish a ``run_interrupted``
  frame via the fan-out so the UI can show a clean "retry" prompt.
  Tool-call rows linked to the same run that are still ``started`` are
  cascaded to ``interrupted`` by
  :func:`backend.runtime.persistence.mark_inbox_interrupted`.
* Rows in ``pending`` never made it to the worker. We rebuild the
  :class:`AgentEvent` and re-enqueue it on the owner's supervisor so
  the loop picks up right where it left off.

Rehydration is idempotent: calling it twice is safe because terminal
statuses are skipped and ``record_inbox_event`` guards against
duplicate rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from backend.runtime.fanout import FanOut, FanOutRegistry, RuntimeEvent
from backend.runtime.persistence import (
    RuntimeRun,
    list_unterminated_inbox_events,
    mark_inbox_completed,
    mark_inbox_interrupted,
    rebuild_agent_event,
)

_TERMINAL_RUN_STATUSES = frozenset({"completed", "error", "interrupted"})
from backend.runtime.supervisor import SupervisorRegistry

logger = logging.getLogger(__name__)


@dataclass
class RehydrationResult:
    """Summary of a rehydration pass."""

    replayed: int = 0
    interrupted: int = 0
    skipped: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "replayed": self.replayed,
            "interrupted": self.interrupted,
            "skipped": self.skipped,
        }


async def _publish_interrupted(
    fanout_registry: FanOutRegistry | None,
    *,
    session_id: str,
    owner_uid: str,
    channel: str,
    run_id: str | None,
    event_id: str,
) -> None:
    if fanout_registry is None:
        return
    fan: FanOut = await fanout_registry.get(session_id)
    try:
        await fan.publish(
            RuntimeEvent(
                kind="run_interrupted",
                session_id=session_id,
                owner_uid=owner_uid,
                channel=channel,
                run_id=run_id or "",
                seq=0,
                payload={
                    "event_id": event_id,
                    "reason": "supervisor_restart",
                    "message": (
                        "This run was interrupted by a supervisor restart. "
                        "Re-send the message to continue."
                    ),
                },
            )
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "rehydration: failed to publish run_interrupted for %s", session_id
        )


async def rehydrate_pending_events(
    registry: SupervisorRegistry,
    session_factory: Callable[[], Any],
    *,
    fanout_registry: FanOutRegistry | None = None,
) -> RehydrationResult:
    """Replay unterminated inbox rows against ``registry``.

    ``session_factory`` is an ``async with`` compatible callable that
    returns an ``AsyncSession``. Persistence errors are logged and
    counted under ``skipped`` — rehydration must never prevent the
    process from finishing startup.
    """
    result = RehydrationResult()
    try:
        async with session_factory() as db:
            rows = await list_unterminated_inbox_events(db)
    except Exception:  # noqa: BLE001
        logger.exception("rehydration: failed to list unterminated events")
        return result

    if not rows:
        logger.info("rehydration: no unterminated inbox rows")
        return result

    logger.info("rehydration: processing %d unterminated inbox rows", len(rows))

    for row in rows:
        try:
            if row.status == "dispatched":
                # Defense-in-depth (Codex PR #342 P2): if the run was
                # already flipped to a terminal status but we crashed
                # before ``mark_inbox_completed`` could commit, don't
                # misreport the run as interrupted. Instead, drag the
                # inbox row up to match the run's terminal state.
                if row.run_id:
                    async with session_factory() as db:
                        run_row = await db.get(RuntimeRun, row.run_id)
                        if run_row is not None and run_row.status in _TERMINAL_RUN_STATUSES:
                            await mark_inbox_completed(
                                db,
                                event_id=row.event_id,
                                status=(
                                    run_row.status
                                    if run_row.status != "completed"
                                    else "completed"
                                ),
                                error=run_row.error,
                            )
                            logger.info(
                                "rehydration: inbox %s reconciled to run=%s "
                                "status=%s (no interrupt frame)",
                                row.event_id,
                                row.run_id,
                                run_row.status,
                            )
                            result.skipped += 1
                            continue

                # The worker was mid-run when the process died. Terminal
                # state + run_interrupted frame so egress can react.
                async with session_factory() as db:
                    await mark_inbox_interrupted(db, event_id=row.event_id)
                await _publish_interrupted(
                    fanout_registry,
                    session_id=row.session_id,
                    owner_uid=row.owner_uid,
                    channel=row.channel,
                    run_id=row.run_id,
                    event_id=row.event_id,
                )
                result.interrupted += 1
                continue

            if row.status == "pending":
                # Never reached the worker — rebuild and re-queue.
                event = rebuild_agent_event(row)
                supervisor = await registry.get(row.owner_uid)
                await supervisor.enqueue(event)
                result.replayed += 1
                continue

            result.skipped += 1
        except Exception:  # noqa: BLE001
            logger.exception(
                "rehydration: failed to process inbox row %s (status=%s)",
                row.event_id,
                row.status,
            )
            result.skipped += 1

    logger.info("rehydration: done (%s)", result.as_dict())
    return result


__all__ = [
    "RehydrationResult",
    "rehydrate_pending_events",
]
