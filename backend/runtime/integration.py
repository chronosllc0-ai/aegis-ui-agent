"""Glue between the FastAPI app and the always-on runtime.

Phase 6 landed the chat-only runtime: the legacy Gemini orchestrator was
deleted, so ``RUNTIME_SUPERVISOR_ENABLED`` now defaults to ``True`` and
the paired ``LEGACY_ORCHESTRATOR`` flag is gone. The env var remains as
a safety switch — operators can still flip it off temporarily if a bad
runtime regression needs to be isolated, but nothing is gated on the
legacy path anymore.

The helpers here are designed to be called from ``main.py``'s startup
/ shutdown / websocket handlers without importing the entire runtime
subsystem into the chat path:

* :func:`runtime_supervisor_enabled` — reads the env flag.
* :func:`ensure_runtime_started` — idempotent app-startup setup.
* :func:`shutdown_runtime` — app-shutdown teardown.
* :func:`get_registry` / :func:`get_fanout_registry` — accessors used
  by ``main.py`` when wiring per-session websocket subscribers.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable, Optional

from backend.runtime.agent_loop import (
    DispatchConfig,
    install_supervisor_dispatch,
)
from backend.runtime.fanout import FanOutRegistry
from backend.runtime.rehydration import rehydrate_pending_events
from backend.runtime.supervisor import SupervisorRegistry

logger = logging.getLogger(__name__)

_registry: SupervisorRegistry | None = None
_fanout_registry: FanOutRegistry | None = None
_rehydration_task: asyncio.Task[None] | None = None


# Tunable via env so tests (or ops incidents) can shorten the retry
# window without patching the module. 30 attempts × 2s ≈ 60s is enough
# for the DB init background task on a cold Railway boot.
_REHYDRATION_ATTEMPTS = int(os.environ.get("RUNTIME_REHYDRATION_ATTEMPTS", "30"))
_REHYDRATION_INTERVAL_SEC = float(
    os.environ.get("RUNTIME_REHYDRATION_INTERVAL_SEC", "2.0")
)


async def _rehydrate_with_retry(
    *,
    registry: SupervisorRegistry,
    session_factory: Callable[[], object],
    fanout_registry: FanOutRegistry | None,
) -> None:
    """Run ``rehydrate_pending_events`` once the DB is actually ready.

    ``main.py`` kicks off ``_initialize_database`` as a background
    task, so the runtime can start *before* the session factory is
    bound. If rehydration runs inline in ``ensure_runtime_started`` it
    either crashes inside ``list_unterminated_inbox_events`` or — worse
    — finds a brand-new schema with no rows and silently declares
    victory, leaving the previous process's pending/dispatched rows
    stuck until the next restart.

    The retry loop here polls for a usable session factory. Once it
    lands, it performs exactly one rehydration pass and exits.
    """

    last_error: BaseException | None = None
    for attempt in range(1, _REHYDRATION_ATTEMPTS + 1):
        try:
            # Probe: opening and immediately closing a session is cheap
            # and raises RuntimeError if ``_session_factory`` is still
            # ``None``.
            async with session_factory() as probe:  # type: ignore[misc]
                await probe.close()
            summary = await rehydrate_pending_events(
                registry,
                session_factory,
                fanout_registry=fanout_registry,
            )
            logger.info(
                "always-on runtime: rehydration summary=%s (attempt %d)",
                summary.as_dict(),
                attempt,
            )
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.info(
                "rehydration: DB not ready yet (attempt %d/%d): %s",
                attempt,
                _REHYDRATION_ATTEMPTS,
                exc,
            )
            await asyncio.sleep(_REHYDRATION_INTERVAL_SEC)

    logger.error(
        "always-on runtime: rehydration giving up after %d attempts "
        "(last error: %s). Pending/dispatched inbox rows will not be "
        "recovered until the next restart.",
        _REHYDRATION_ATTEMPTS,
        last_error,
    )


_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def runtime_supervisor_enabled() -> bool:
    """``True`` when the always-on runtime supervisor should own chat.

    Default is ``True`` as of Phase 6 — the legacy Gemini orchestrator
    was deleted so there is no fallback. Operators can set
    ``RUNTIME_SUPERVISOR_ENABLED=false`` to temporarily disable the
    supervisor during incident triage, but chat will be unavailable
    until it's turned back on.
    """
    return _env_flag("RUNTIME_SUPERVISOR_ENABLED", default=True)


async def ensure_runtime_started(
    *,
    chat_message_persister=None,
) -> None:
    """Create the supervisor registry and install the dispatch hook.

    Safe to call on every startup; the registry is only created once.
    When the feature flag is off this is a no-op.

    ``chat_message_persister`` is an optional callable forwarded into
    :class:`DispatchConfig` so the agent loop can land assistant
    replies in the chat-session row even when no websocket bridge is
    attached (heartbeat / queued automation paths).
    """
    global _registry, _fanout_registry
    if not runtime_supervisor_enabled():
        logger.info(
            "always-on runtime: RUNTIME_SUPERVISOR_ENABLED=false — chat dispatch disabled"
        )
        return
    if _registry is not None:
        return

    _registry = SupervisorRegistry()
    _fanout_registry = FanOutRegistry()

    def _session_ctx():
        """Late-bound DB session context.

        Runtime startup runs before DB init on some paths (DB init is
        kicked off as a background task). Reading
        ``backend.database._session_factory`` at install time would
        bake ``None`` into the dispatch config forever, silently
        disabling :data:`runtime_runs` persistence for the whole
        process. Resolving the factory lazily every run lets
        persistence turn on the instant the DB is ready.
        """
        # Import inside the factory so a not-yet-initialised database
        # module does not cache an early ``None`` binding.
        from backend import database as _db  # noqa: WPS433 (late import is intentional)

        factory = getattr(_db, "_session_factory", None)
        if factory is None:
            raise RuntimeError("Database session factory is not initialised")
        return factory()

    install_supervisor_dispatch(
        _registry,
        DispatchConfig(
            fanout_registry=_fanout_registry,
            # Always pass the lazy accessor. The dispatch hook already
            # catches persistence errors and logs them, so an "early"
            # event before DB init just records no run row; once the DB
            # is up every subsequent run persists normally.
            session_factory=_session_ctx,
            chat_message_persister=chat_message_persister,
        ),
    )
    # Phase 7: enable inbox durability on every supervisor the registry
    # spawns from now on. ``SessionSupervisor.enqueue`` will persist a
    # row per event before pushing to the priority queue.
    _registry.set_persistence_factory(_session_ctx)
    logger.info("always-on runtime: supervisor + dispatch hook installed")

    # Phase 7: boot rehydration runs as a retrying background task so
    # it does not race ``_initialize_database`` (Codex PR #342 P1).
    # Startup fires DB init as its own background task; reading
    # ``_session_factory`` here can easily find ``None``. If we
    # swallowed that error synchronously, ``_registry`` would be
    # installed and any future ``ensure_runtime_started`` call would
    # return early, never recovering pending/dispatched rows until
    # another process restart.
    global _rehydration_task
    if _rehydration_task is None or _rehydration_task.done():
        _rehydration_task = asyncio.create_task(
            _rehydrate_with_retry(
                registry=_registry,
                session_factory=_session_ctx,
                fanout_registry=_fanout_registry,
            ),
            name="runtime-rehydration",
        )


async def shutdown_runtime() -> None:
    """Drain every supervisor and drop the registries."""
    global _registry, _fanout_registry, _rehydration_task
    if _rehydration_task is not None and not _rehydration_task.done():
        _rehydration_task.cancel()
        try:
            await _rehydration_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    _rehydration_task = None
    if _registry is None:
        return
    try:
        await _registry.shutdown()
    except Exception:  # noqa: BLE001
        logger.exception("Supervisor registry shutdown failed")
    _registry = None
    _fanout_registry = None


def get_registry() -> Optional[SupervisorRegistry]:
    return _registry


def get_fanout_registry() -> Optional[FanOutRegistry]:
    return _fanout_registry


__all__ = [
    "runtime_supervisor_enabled",
    "ensure_runtime_started",
    "shutdown_runtime",
    "get_registry",
    "get_fanout_registry",
]
