"""Regression tests for the Phase 2 PR review fixes.

Each test corresponds to a bot-reported finding on PR #336:

* ``kilo-code critical #1`` — ``build_dispatch_hook`` must not re-raise
  after it has already emitted an ``error`` event, because the
  supervisor worker is shared across every channel for that user.
* ``kilo-code critical #2`` — ``exec_shell`` must reject obviously
  destructive commands via a pattern denylist, and must be droppable
  via ``RUNTIME_EXEC_SHELL_ENABLED=false``.
* ``codex P1`` — supervisor chat payloads must carry ``settings`` and
  ``memory_mode`` so :class:`ToolContext` mirrors the legacy path.
* ``codex P2`` — the runtime dispatch config must tolerate a DB that
  initialises after runtime startup.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from agents import Agent
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText

from backend.runtime import AgentEvent, EventKind, SessionSupervisor
from backend.runtime.agent_loop import DispatchConfig, build_dispatch_hook
from backend.runtime.fanout import FanOutRegistry, RuntimeEvent, Subscriber
from backend.runtime.tools.native import (
    EXEC_SHELL_DENY_PATTERNS,
    NATIVE_TOOL_NAMES,
    exec_shell,
    get_enabled_native_tools,
)


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ----------------------------------------------------------------------
# kilo-code critical #1: dispatch hook must swallow exceptions
# ----------------------------------------------------------------------


class _BoomModel(Model):
    """Stub model that always raises on invocation."""

    async def get_response(self, *a: Any, **kw: Any) -> ModelResponse:
        raise RuntimeError("synthetic provider failure")

    async def stream_response(self, *a: Any, **kw: Any):  # pragma: no cover
        raise RuntimeError("synthetic provider failure")
        yield  # type: ignore[unreachable]


def test_dispatch_hook_does_not_propagate_runner_exception() -> None:
    """A bad run must not poison the supervisor worker for the next event."""

    received: list[RuntimeEvent] = []
    processed_after_boom: list[str] = []

    async def collector(event: RuntimeEvent) -> None:
        received.append(event)

    async def scenario() -> None:
        fanout = FanOutRegistry()
        supervisor = SessionSupervisor("user-review-1")

        def build_agent(session, ctx):
            return Agent(name="boom", instructions="boom", tools=[], model=_BoomModel())

        hook = build_dispatch_hook(
            DispatchConfig(
                fanout_registry=fanout,
                build_agent_fn=build_agent,
                session_factory=None,
            )
        )
        supervisor.install_dispatch(hook)
        supervisor.start()
        # Subscribe to the session fan-out before dispatching so we
        # receive the error + run_completed events.
        fan = await fanout.get("agent:main:web:user-review-1")
        await fan.subscribe(Subscriber(name="t", callback=collector))

        # First event: the model explodes. The dispatch hook must catch,
        # emit "error" + "run_completed", and NOT re-raise.
        await supervisor.enqueue(
            AgentEvent(
                owner_uid="user-review-1",
                channel="web",
                kind=EventKind.CHAT_MESSAGE,
                payload={"text": "hi", "settings": {}, "memory_mode": "files"},
            )
        )

        # Wait for run_completed from the failed event.
        for _ in range(400):
            if any(e.kind == "run_completed" for e in received):
                break
            await asyncio.sleep(0.01)

        # Second event: after the failure, the supervisor worker must
        # still be alive. Swap in a recording hook.
        async def _second_hook(sup, event, sess):
            processed_after_boom.append(event.event_id)

        supervisor.install_dispatch(_second_hook)
        await supervisor.enqueue(
            AgentEvent(
                owner_uid="user-review-1",
                channel="web",
                kind=EventKind.CHAT_MESSAGE,
                payload={"text": "still alive?"},
            )
        )
        for _ in range(400):
            if processed_after_boom:
                break
            await asyncio.sleep(0.01)
        await supervisor.stop(drain=True)

    _run(scenario())
    # Worker stayed alive and processed event #2 even though event #1 blew up.
    assert processed_after_boom, "supervisor worker died after a failing run"
    # And the error was emitted to the subscriber rather than swallowed silently.
    kinds = [e.kind for e in received]
    assert "error" in kinds, f"no error event emitted; saw {kinds}"
    assert "run_completed" in kinds


# ----------------------------------------------------------------------
# kilo-code critical #2: exec_shell denylist + opt-out flag
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "rm -rf /",
        "rm -rf /*",
        "rm -fr /",
        "sudo rm -rf /",
        ":(){ :|:& };:",
        "mkfs.ext4 /dev/sda1",
        "dd if=/dev/zero of=/dev/sda bs=1M",
        "shutdown -h now",
        "cat /etc/passwd",
        "cat /etc/shadow",
    ],
)
def test_exec_shell_denylist_matches_destructive_commands(cmd: str) -> None:
    """Every obviously destructive command pattern must be caught by the denylist."""
    assert any(pat.search(cmd) for pat in EXEC_SHELL_DENY_PATTERNS), cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "ls -la",
        "python3 build.py",
        "git status",
        "rm temp.txt",
        "echo hello",
    ],
)
def test_exec_shell_denylist_allows_benign_commands(cmd: str) -> None:
    assert not any(pat.search(cmd) for pat in EXEC_SHELL_DENY_PATTERNS), cmd


def test_exec_shell_can_be_disabled_via_env_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting RUNTIME_EXEC_SHELL_ENABLED=false drops the tool entirely."""
    monkeypatch.setenv("RUNTIME_EXEC_SHELL_ENABLED", "false")
    names = {getattr(t, "name", None) for t in get_enabled_native_tools()}
    assert "exec_shell" not in names
    # Everything else is still there.
    assert (NATIVE_TOOL_NAMES - {"exec_shell"}).issubset(names)


def test_exec_shell_default_includes_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUNTIME_EXEC_SHELL_ENABLED", raising=False)
    names = {getattr(t, "name", None) for t in get_enabled_native_tools()}
    assert "exec_shell" in names


# ----------------------------------------------------------------------
# codex P1: supervisor chat payload must carry settings + memory_mode
# ----------------------------------------------------------------------


def test_main_supervisor_dispatch_forwards_settings_and_memory_mode() -> None:
    """Sanity check that the main.py enqueue path includes the fix.

    We can't import main.py without a full app, so instead assert on
    the source — this is a cheap canary that blocks regression of the
    codex P1 finding.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(repo_root, "main.py"), "r", encoding="utf-8") as fh:
        src = fh.read()
    # Window around the dispatch enqueue call.
    start = src.index("_runtime_supervisor_dispatch_chat")
    snippet = src[start : start + 2500]
    assert '"settings": runtime_settings' in snippet, snippet
    assert '"memory_mode": memory_mode' in snippet, snippet


# ----------------------------------------------------------------------
# codex P2: session_factory must resolve lazily
# ----------------------------------------------------------------------


def test_integration_installs_lazy_session_factory() -> None:
    """The integration module must pass a callable session_factory
    regardless of whether the DB has been initialised yet."""
    from backend.runtime import integration as integ

    # Reach into the module to inspect the helper without running the
    # full startup sequence (which requires an event loop + DB URL).
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(
        os.path.join(repo_root, "backend", "runtime", "integration.py"),
        "r",
        encoding="utf-8",
    ) as fh:
        src = fh.read()
    # The hook must ALWAYS install session_factory=_session_ctx, not
    # `_session_ctx if ... else None` (the old regression).
    assert "session_factory=_session_ctx," in src
    assert "_session_ctx if _session_factory" not in src
    # And the factory must resolve the DB module lazily each call.
    assert "from backend import database as _db" in src

    # Smoke: the module exposes the expected accessors.
    assert callable(integ.ensure_runtime_started)
    assert callable(integ.shutdown_runtime)
