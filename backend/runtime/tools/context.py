"""Runtime tool context.

Every :mod:`backend.runtime.tools.native` tool receives a
``RunContextWrapper[ToolContext]`` as its first parameter. The context
carries everything the legacy tool implementations used to read off
``UniversalNavigator``:

- session id + owner uid (Postgres + workspace keys),
- the merged websocket/runtime settings blob (for memory mode, integration
  tokens, permissions, etc.),
- async callbacks the model can use to pause for the user (ask /
  confirm) or hand off to a sub-agent.

Phase 2 does *not* wire the pause callbacks end-to-end — those land when
the ingress layer is rewritten. Tools that need them but have none wired
return a deterministic ``"<tool> not available in this context"`` string
so the model can recover.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


AskUserInputFn = Callable[[str, list[str]], Awaitable[str]]
"""(question, options) → user's answer."""

# NOTE: `HandoffFn` and `on_handoff_to_user` were removed in Phase 5 along
# with the `handoff_to_user` native tool. The runtime is chat-only — there is
# no frontend affordance to resume a manual browser handoff. If HITL browser
# steering is reintroduced, wire it through a dedicated operator surface
# rather than resurrecting these callbacks on the per-run context.

SpawnSubagentFn = Callable[[str, str], Awaitable[str]]
"""(instruction, model) → sub-agent id."""

MessageSubagentFn = Callable[[str, str], Awaitable[bool]]
"""(sub_id, message) → success bool."""

StepEmitterFn = Callable[[dict[str, Any]], Awaitable[None]]
"""Push a structured step event to whichever egress cares."""


@dataclass
class ToolContext:
    """Per-run tool context passed to every native tool."""

    session_id: str
    """Session workspace / memory key (``agent:main:{channel}:{owner_uid}``)."""

    owner_uid: str | None
    """Authenticated user uid. Required for DB-backed tools (memory, cron)."""

    channel: str = "web"
    """Which surface produced the event this run is responding to."""

    settings: dict[str, Any] = field(default_factory=dict)
    """Merged runtime settings — integrations, permissions, agent mode, etc."""

    memory_mode: str = "files"
    """``files`` | ``db`` | ``hybrid`` — matches legacy navigator semantics."""

    memory_long_term_main_only: bool = False
    is_main_session: bool = True

    on_ask_user_input: AskUserInputFn | None = None
    on_spawn_subagent: SpawnSubagentFn | None = None
    on_message_subagent: MessageSubagentFn | None = None
    on_step: StepEmitterFn | None = None

    extras: dict[str, Any] = field(default_factory=dict)
    """Free-form slot for plumbing future per-run metadata without a schema bump."""

    def should_include_long_term_memory(self) -> bool:
        if not self.memory_long_term_main_only:
            return True
        return self.is_main_session
