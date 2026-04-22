"""Always-on agent runtime.

This package hosts the new always-on runtime described in ``PLAN.md``.

Phase 1 scope (this module set): scaffolding only. The modules here define
the public interfaces and minimal in-memory implementations so that
subsequent phases can swap in real behavior without changing call sites.

Nothing in this package is wired into the main application yet. Callers
should treat every module as experimental and gate any integration behind
the ``RUNTIME_SUPERVISOR_ENABLED`` feature flag until Phase 2 lands the
OpenAI Agents SDK loop.
"""

from backend.runtime.events import AgentEvent, EventKind, EventPriority
from backend.runtime.session import ChannelSession, ChannelSessionKey
from backend.runtime.supervisor import SessionSupervisor, SupervisorRegistry

__all__ = [
    "AgentEvent",
    "EventKind",
    "EventPriority",
    "ChannelSession",
    "ChannelSessionKey",
    "SessionSupervisor",
    "SupervisorRegistry",
]
