"""Agents SDK runner wiring for the always-on runtime.

Phase 2 introduces three public helpers:

* :func:`build_agent` — constructs an :class:`agents.Agent` with the
  native tool manifest and a LiteLLM-backed model shim so downstream
  providers (OpenAI, Anthropic, Gemini, xAI, ...) all share one runner.
* :func:`build_dispatch_hook` — produces the :data:`DispatchHook`
  callable that :class:`~backend.runtime.supervisor.SessionSupervisor`
  installs. The hook turns an :class:`AgentEvent` into a
  ``Runner.run_streamed`` call, streams deltas to the fan-out, and
  persists the run's event log.
* :func:`install_supervisor_dispatch` — bolts the hook onto a
  :class:`SupervisorRegistry` so every per-user supervisor uses the new
  loop.

The module is the single gate between the legacy websocket chat flow
and the new runtime. Everything else stays untouched until Phase 3
brings MCP and Phase 4 brings the connectors.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel
from agents.items import ModelResponse
from agents.models.interface import Model

from backend.runtime.events import AgentEvent, EventKind
from backend.runtime.fanout import FanOut, FanOutRegistry, RuntimeEvent
from backend.runtime.persistence import (
    new_run_id,
    record_event,
    record_run_end,
    record_run_start,
)
from backend.runtime.session import ChannelSession
from backend.runtime.supervisor import DispatchHook, SessionSupervisor, SupervisorRegistry
from backend.runtime.tools.context import ToolContext
from backend.runtime.tools.mcp_host import MCPToolProvider, SpecLoader
from backend.runtime.tools.native import NATIVE_TOOLS, get_enabled_native_tools

logger = logging.getLogger(__name__)


DEFAULT_MODEL_ENV = "RUNTIME_SUPERVISOR_MODEL"
DEFAULT_MODEL_FALLBACK = "openai/gpt-5"

DEFAULT_INSTRUCTIONS = (
    "You are Aegis, a browser-first AI operator running inside an "
    "always-on session. Use the native tools to read and write the "
    "session workspace, exercise the user's memories, manage automations, "
    "and interact with GitHub. Browser navigation tools are reserved for "
    "a separate channel and are not available in this context. Always "
    "keep tool calls minimal and explain the outcome in natural language "
    "when you return to the user."
)


def _resolve_model(setting: str | None) -> Model:
    """Choose a model for the runner.

    * When ``OPENAI_API_KEY`` is configured, default to LiteLLM's OpenAI
      route (``openai/<name>``) so everything flows through a single shim.
    * The ``RUNTIME_SUPERVISOR_MODEL`` env var overrides the default
      without touching code.
    """
    model_id = (setting or os.getenv(DEFAULT_MODEL_ENV) or DEFAULT_MODEL_FALLBACK).strip()
    if not model_id:
        model_id = DEFAULT_MODEL_FALLBACK
    return LitellmModel(model=model_id)


def build_agent(
    *,
    session: ChannelSession,
    tools: Sequence[Any] | None = None,
    instructions: str | None = None,
    model: Model | str | None = None,
) -> Agent:
    """Construct an :class:`agents.Agent` for the given channel session.

    Callers that want a deterministic test model can pass a pre-built
    :class:`Model` instance directly. String overrides are forwarded to
    LiteLLM.
    """
    if isinstance(model, Model):
        resolved_model: Model | str = model
    elif isinstance(model, str) and model.strip():
        resolved_model = _resolve_model(model)
    else:
        resolved_model = _resolve_model(None)

    return Agent(
        name=f"aegis-{session.channel}",
        instructions=instructions or DEFAULT_INSTRUCTIONS,
        tools=list(tools) if tools is not None else get_enabled_native_tools(),
        model=resolved_model,
    )


# ----------------------------------------------------------------------
# Dispatch hook
# ----------------------------------------------------------------------


@dataclass
class DispatchConfig:
    """Tuning knobs for the dispatch hook."""

    max_turns: int = 10
    fanout_registry: FanOutRegistry | None = None
    session_factory: Any = None  # async context manager returning AsyncSession
    build_agent_fn: Callable[[ChannelSession, ToolContext], Agent] | None = None
    instructions: str | None = None
    model: Model | str | None = None
    mcp_spec_loader: SpecLoader | None = None
    """Optional per-user MCP spec loader.

    When set, each supervisor gets its own :class:`MCPToolProvider`
    (lazily spawned on first dispatch, torn down in
    :meth:`SessionSupervisor.stop`). When ``None``, MCP tools are not
    attached and the agent runs with native tools only.
    """


def _extract_text(event: AgentEvent) -> str:
    payload = event.payload or {}
    for key in ("text", "instruction", "prompt", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _summarize_new_items(result_new_items: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in result_new_items:
        kind = getattr(item, "type", None) or item.__class__.__name__
        record: dict[str, Any] = {"type": kind}
        raw_item = getattr(item, "raw_item", None)
        if raw_item is not None:
            name = getattr(raw_item, "name", None)
            call_id = getattr(raw_item, "call_id", None)
            arguments = getattr(raw_item, "arguments", None)
            if name:
                record["name"] = name
            if call_id:
                record["call_id"] = call_id
            if isinstance(arguments, str):
                record["arguments"] = arguments
        output = getattr(item, "output", None)
        if isinstance(output, str):
            record["output"] = output[:2000]
        text = getattr(item, "text", None)
        if isinstance(text, str):
            record["text"] = text[:2000]
        out.append(record)
    return out


async def _publish(fan: FanOut | None, event: RuntimeEvent) -> None:
    if fan is None:
        return
    try:
        await fan.publish(event)
    except Exception:  # noqa: BLE001
        logger.exception("FanOut publish failed for %s", event.kind)


async def _maybe_record(
    session_factory: Any,
    *,
    run_id: str,
    seq: int,
    kind: str,
    payload: dict[str, Any],
) -> None:
    if session_factory is None:
        return
    try:
        async with session_factory() as session:
            await record_event(
                session, run_id=run_id, seq=seq, kind=kind, payload=payload
            )
    except Exception:  # noqa: BLE001
        logger.exception("record_event failed kind=%s run=%s", kind, run_id)


def _default_build_agent(
    session: ChannelSession,
    ctx: ToolContext,
    config: DispatchConfig,
    mcp_tools: Sequence[Any] | None = None,
) -> Agent:
    tools: list[Any] = list(get_enabled_native_tools())
    if mcp_tools:
        tools.extend(mcp_tools)
    return build_agent(
        session=session,
        tools=tools,
        instructions=config.instructions,
        model=config.model,
    )


async def _ensure_mcp_provider(
    supervisor: SessionSupervisor,
    config: DispatchConfig,
) -> MCPToolProvider | None:
    """Lazily create an :class:`MCPToolProvider` bound to ``supervisor``.

    The provider is cached on a private attribute so every dispatch for
    this user reuses the same underlying MCP sessions. A teardown hook
    on the supervisor closes it when the supervisor stops.
    """
    if config.mcp_spec_loader is None:
        return None
    existing: MCPToolProvider | None = getattr(supervisor, "_mcp_provider", None)
    if existing is not None:
        return existing
    provider = MCPToolProvider(
        owner_uid=supervisor.owner_uid,
        spec_loader=config.mcp_spec_loader,
    )
    supervisor._mcp_provider = provider  # type: ignore[attr-defined]
    supervisor.register_teardown(provider.aclose)
    return provider


def build_dispatch_hook(config: DispatchConfig | None = None) -> DispatchHook:
    """Return a dispatch hook that runs the Agents SDK loop."""

    cfg = config or DispatchConfig()

    async def dispatch(
        supervisor: SessionSupervisor,
        event: AgentEvent,
        session: ChannelSession,
    ) -> None:
        if event.kind != EventKind.CHAT_MESSAGE:
            logger.debug(
                "runtime_dispatch: skipping non-chat event kind=%s session=%s",
                event.kind.value,
                session.session_id,
            )
            return

        text = _extract_text(event)
        if not text:
            logger.debug("runtime_dispatch: empty chat payload on %s", session.session_id)
            return

        fan: FanOut | None = None
        if cfg.fanout_registry is not None:
            fan = await cfg.fanout_registry.get(session.session_id)

        run_id = new_run_id()
        seq = 0

        async def emit(kind: str, payload: dict[str, Any]) -> None:
            nonlocal seq
            seq += 1
            await _publish(
                fan,
                RuntimeEvent(
                    kind=kind,
                    session_id=session.session_id,
                    owner_uid=session.owner_uid,
                    channel=session.channel,
                    run_id=run_id,
                    seq=seq,
                    payload=payload,
                ),
            )
            await _maybe_record(
                cfg.session_factory,
                run_id=run_id,
                seq=seq,
                kind=kind,
                payload=payload,
            )

        if cfg.session_factory is not None:
            try:
                async with cfg.session_factory() as sess:
                    await record_run_start(
                        sess,
                        run_id=run_id,
                        owner_uid=session.owner_uid,
                        channel=session.channel,
                        session_id=session.session_id,
                        model=str(cfg.model) if cfg.model else None,
                    )
            except Exception:  # noqa: BLE001
                logger.exception("record_run_start failed run=%s", run_id)

        await emit(
            "run_started",
            {"text": text, "channel": session.channel, "owner_uid": session.owner_uid},
        )
        await emit("user_message", {"text": text})

        tool_ctx = ToolContext(
            session_id=session.session_id,
            owner_uid=session.owner_uid,
            channel=session.channel,
            settings=dict(event.payload.get("settings") or {}),
            memory_mode=str(event.payload.get("memory_mode") or "files"),
            is_main_session=True,
        )

        mcp_tools: list[Any] = []
        provider = await _ensure_mcp_provider(supervisor, cfg)
        if provider is not None:
            try:
                mcp_tools = list(await provider.get_tools())
            except Exception:  # noqa: BLE001
                logger.exception(
                    "runtime_dispatch: MCP provider failed for %s",
                    session.owner_uid,
                )

        agent_builder = cfg.build_agent_fn or (
            lambda s, c: _default_build_agent(s, c, cfg, mcp_tools)
        )
        agent = agent_builder(session, tool_ctx)

        status = "completed"
        error_text: str | None = None
        try:
            result = await Runner.run(
                agent,
                text,
                context=tool_ctx,
                max_turns=cfg.max_turns,
            )
            for item_record in _summarize_new_items(result.new_items):
                kind = "tool_call" if item_record["type"] == "tool_call_item" else (
                    "tool_result" if item_record["type"] == "tool_call_output_item" else
                    "model_message" if item_record["type"] == "message_output_item" else
                    "trace"
                )
                await emit(kind, item_record)
            final_text = str(result.final_output) if result.final_output is not None else ""
            await emit("final_message", {"text": final_text})
        except Exception as exc:  # noqa: BLE001
            # Critical: do NOT re-raise. The supervisor worker serves
            # every channel session for this user — propagating the
            # exception would make a single bad run silently degrade
            # the entire per-user loop (the supervisor catches it, but
            # tool errors would bubble past persistence/fan-out).
            # Instead we fully own the error here: record it on the run
            # row, stream it to subscribers, and let the worker pick up
            # the next event.
            status = "error"
            error_text = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "runtime_dispatch: Runner.run failed run=%s session=%s",
                run_id,
                session.session_id,
            )
            await emit("error", {"message": error_text})
        finally:
            await emit("run_completed", {"status": status})
            if cfg.session_factory is not None:
                try:
                    async with cfg.session_factory() as sess:
                        await record_run_end(
                            sess, run_id=run_id, status=status, error=error_text
                        )
                except Exception:  # noqa: BLE001
                    logger.exception("record_run_end failed run=%s", run_id)

    return dispatch


def install_supervisor_dispatch(
    registry: SupervisorRegistry,
    config: DispatchConfig | None = None,
) -> DispatchHook:
    """Wire the Agents SDK dispatch hook onto every supervisor in ``registry``.

    Both existing supervisors and future ones (created via
    :meth:`SupervisorRegistry.get`) will use the new loop.
    """

    hook = build_dispatch_hook(config)
    registry._dispatch = hook  # type: ignore[attr-defined]
    for supervisor in registry._supervisors.values():  # type: ignore[attr-defined]
        supervisor.install_dispatch(hook)
    return hook


__all__ = [
    "DEFAULT_MODEL_ENV",
    "DEFAULT_MODEL_FALLBACK",
    "DispatchConfig",
    "build_agent",
    "build_dispatch_hook",
    "install_supervisor_dispatch",
]
