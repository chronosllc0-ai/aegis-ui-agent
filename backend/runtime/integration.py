"""Glue between the FastAPI app and the always-on runtime.

Phase 2 is deliberately minimal: one feature flag
(``RUNTIME_SUPERVISOR_ENABLED``) turns on a parallel chat path. When the
flag is off, everything runs exactly as it did in Phase 1 — the legacy
Gemini orchestrator owns websocket chat.

The helpers here are designed to be called from ``main.py``'s startup
/ shutdown / websocket handlers without importing the entire runtime
subsystem into the chat path:

* :func:`runtime_supervisor_enabled` — reads the env flag.
* :func:`legacy_orchestrator_enabled` — reads the paired flag
  (default ``true``; must stay the deployed default).
* :func:`ensure_runtime_started` — idempotent app-startup setup.
* :func:`shutdown_runtime` — app-shutdown teardown.
* :func:`get_registry` / :func:`get_fanout_registry` — accessors used
  by ``main.py`` when wiring per-session websocket subscribers.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from backend.runtime.agent_loop import (
    DispatchConfig,
    install_supervisor_dispatch,
)
from backend.runtime.fanout import FanOutRegistry
from backend.runtime.supervisor import SupervisorRegistry

logger = logging.getLogger(__name__)

_registry: SupervisorRegistry | None = None
_fanout_registry: FanOutRegistry | None = None


_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def runtime_supervisor_enabled() -> bool:
    """``True`` when ``RUNTIME_SUPERVISOR_ENABLED`` is truthy."""
    return _env_flag("RUNTIME_SUPERVISOR_ENABLED", default=False)


def legacy_orchestrator_enabled() -> bool:
    """``True`` when the legacy Gemini orchestrator is allowed.

    Default ``True`` so existing deploys keep behaving exactly as before.
    """
    return _env_flag("LEGACY_ORCHESTRATOR", default=True)


async def ensure_runtime_started() -> None:
    """Create the supervisor registry and install the dispatch hook.

    Safe to call on every startup; the registry is only created once.
    When the feature flag is off this is a no-op.
    """
    global _registry, _fanout_registry
    if not runtime_supervisor_enabled():
        logger.info(
            "always-on runtime: RUNTIME_SUPERVISOR_ENABLED=false — staying on legacy path"
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
        ),
    )
    logger.info("always-on runtime: supervisor + dispatch hook installed")


async def shutdown_runtime() -> None:
    """Drain every supervisor and drop the registries."""
    global _registry, _fanout_registry
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
    "legacy_orchestrator_enabled",
    "ensure_runtime_started",
    "shutdown_runtime",
    "get_registry",
    "get_fanout_registry",
]
