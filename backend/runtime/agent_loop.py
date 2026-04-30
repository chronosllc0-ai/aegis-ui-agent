"""Agents SDK runner wiring for the always-on runtime."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Sequence

from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel
from agents.models.interface import Model

from backend.runtime.context_window import build_prepared_context, maybe_create_checkpoint
from backend.runtime.events import AgentEvent, EventKind
from backend.runtime.fanout import FanOut, FanOutRegistry, RuntimeEvent
from backend.runtime.persistence import (
    finalize_run_and_inbox,
    mark_inbox_dispatched,
    new_run_id,
    record_event,
    record_run_start,
    record_tool_call_completed,
    record_tool_call_started,
)
from backend.runtime.session import ChannelSession
from backend.runtime.supervisor import DispatchHook, SessionSupervisor, SupervisorRegistry
from backend.runtime.tools.context import ToolContext
from backend.runtime.tools.connectors import ConnectorLoader, load_connector_tools
from backend.runtime.tools.mcp_host import MCPToolProvider, SpecLoader
from backend.runtime.tools.native import get_enabled_native_tools

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ENV = "RUNTIME_SUPERVISOR_MODEL"
DEFAULT_MODEL_FALLBACK = "openai/gpt-5"

DEFAULT_INSTRUCTIONS = (
    "You are Aegis, an always-on AI coworker running in a persistent "
    "server-side session. The browser is only one tool among many, not "
    "the runtime. Use native tools, MCP tools, OAuth connector tools, "
    "memory, workspace files, automations, and GitHub carefully. Keep "
    "tool calls minimal, preserve user intent across turns, and explain "
    "outcomes in natural language when returning to the user."
)

LITELLM_PROVIDER_PREFIX_BY_SETTINGS_PROVIDER = {
    # The Chronos catalogue is backed by OpenRouter-style model IDs.
    # LiteLLM needs the routing provider prepended, e.g.
    # ``openrouter/nvidia/nemotron-...``.
    "chronos": "openrouter",
    "openrouter": "openrouter",
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "gemini",
    "xai": "xai",
    "fireworks": "fireworks_ai",
}


def normalize_runtime_model(provider: str | None, model_id: str | None) -> str | None:
    """Convert frontend provider/model settings into a LiteLLM model string.

    The browser stores provider IDs from ``frontend/src/lib/models.ts``.
    The always-on runtime uses ``LitellmModel``, which expects provider
    routing prefixes such as ``fireworks_ai/`` or ``openrouter/``.
    """
    model = (model_id or "").strip()
    if not model:
        return None

    settings_provider = (provider or "").strip().lower()
    litellm_prefix = LITELLM_PROVIDER_PREFIX_BY_SETTINGS_PROVIDER.get(settings_provider)
    if not litellm_prefix:
        return model
    if model.startswith(f"{litellm_prefix}/"):
        return model
    return f"{litellm_prefix}/{model}"


def resolve_runtime_model_setting(
    settings: Mapping[str, Any] | None,
    fallback: Model | str | None = None,
) -> Model | str | None:
    """Resolve the per-dispatch model, preserving static fallback only if unset."""
    runtime_settings = settings or {}
    selected = normalize_runtime_model(
        str(runtime_settings.get("provider") or ""),
        str(runtime_settings.get("model") or ""),
    )
    return selected or fallback


def _runtime_model_label(model: Model | str | None) -> str | None:
    if isinstance(model, str):
        return model
    if model is None:
        return None
    return model.__class__.__name__


def _resolve_model(setting: str | None) -> Model:
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
    """Construct an Agents SDK Agent for the given channel session."""
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


@dataclass
class DispatchConfig:
    """Tuning knobs for the dispatch hook."""

    max_turns: int = 10
    fanout_registry: FanOutRegistry | None = None
    session_factory: Any = None
    build_agent_fn: Callable[[ChannelSession, ToolContext], Agent] | None = None
    instructions: str | None = None
    model: Model | str | None = None
    mcp_spec_loader: SpecLoader | None = None
    connector_loader: ConnectorLoader | None = None
    context_window_tokens: int | None = None
    compact_threshold_pct: int | None = None
    # Optional callable that persists an assistant ``final_message``
    # to the chat-session log keyed on ``(owner_uid, ws_session_id)``.
    # Invoked by ``dispatch`` after ``Runner.run`` succeeds, so the
    # heartbeat (and any other no-websocket trigger) still drops the
    # assistant reply into the right chat thread when no fan-out
    # subscriber is attached. Returning ``True`` indicates the write
    # was performed; the WS bridge uses the same dedupe LRU to avoid
    # double-writing when both paths are alive.
    #
    # Signature: ``(run_id, owner_uid, ws_session_id, text, metadata)
    # -> Awaitable[bool]``.
    chat_message_persister: (
        Callable[[str, str, str, str, dict[str, Any]], Awaitable[bool]] | None
    ) = None


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
            await record_event(session, run_id=run_id, seq=seq, kind=kind, payload=payload)
    except Exception:  # noqa: BLE001
        logger.exception("record_event failed kind=%s run=%s", kind, run_id)


def _tool_name(tool: Any) -> str | None:
    name = getattr(tool, "name", None)
    if isinstance(name, str):
        return name
    return None


def _agent_tools(agent: Agent) -> Sequence[Any]:
    tools = getattr(agent, "tools", None)
    if isinstance(tools, Sequence):
        return tools
    return []


def _default_build_agent(
    session: ChannelSession,
    ctx: ToolContext,
    config: DispatchConfig,
    mcp_tools: Sequence[Any] | None = None,
    connector_tools: Sequence[Any] | None = None,
) -> Agent:
    """Compose native + MCP + connector tools into a single Agent.

    Native tools win over MCP tools; MCP tools win over connector tools.
    This prevents OAuth-generated GitHub tool names from shadowing the
    legacy PAT-backed native GitHub tools.
    """
    tools: list[Any] = list(get_enabled_native_tools())
    seen: set[str] = {n for n in (_tool_name(t) for t in tools) if n}

    def _extend_unique(extra: Sequence[Any], source: str) -> None:
        shadowed: list[str] = []
        for tool in extra:
            name = _tool_name(tool)
            if name is None:
                tools.append(tool)
                continue
            if name in seen:
                shadowed.append(name)
                continue
            seen.add(name)
            tools.append(tool)
        if shadowed:
            logger.warning(
                "agent_loop: dropped %d %s tool(s) shadowed by earlier layer: %s",
                len(shadowed),
                source,
                ", ".join(sorted(shadowed)),
            )

    if mcp_tools:
        _extend_unique(mcp_tools, "MCP")
    if connector_tools:
        _extend_unique(connector_tools, "connector")
    runtime_model = resolve_runtime_model_setting(ctx.settings, config.model)
    return build_agent(session=session, tools=tools, instructions=config.instructions, model=runtime_model)


async def _ensure_mcp_provider(
    supervisor: SessionSupervisor,
    config: DispatchConfig,
) -> MCPToolProvider | None:
    existing: MCPToolProvider | None = getattr(supervisor, "_mcp_provider", None)
    if existing is not None:
        return existing
    provider = MCPToolProvider(owner_uid=supervisor.owner_uid, spec_loader=config.mcp_spec_loader)
    supervisor._mcp_provider = provider  # type: ignore[attr-defined]
    supervisor.register_teardown(provider.aclose)
    return provider


def _tool_names_for_meter(agent: Agent) -> list[str]:
    return sorted({name for name in (_tool_name(t) for t in _agent_tools(agent)) if name})


def _instructions_for_meter(agent: Agent, config: DispatchConfig) -> str:
    value = config.instructions or getattr(agent, "instructions", None) or DEFAULT_INSTRUCTIONS
    return str(value)


def _checkpoint_prompt(*, instructions: str, checkpoint: dict[str, Any], current_text: str) -> str:
    summary = str(checkpoint.get("summary") or "").strip()
    checkpoint_id = str(checkpoint.get("checkpoint_id") or "runtime-checkpoint")
    body = summary or f"CHECKPOINT: see persisted checkpoint {checkpoint_id}."
    return "\n\n".join(
        [
            instructions.strip(),
            "Previous compacted checkpoint:\n" + body,
            "Current user message:\n" + current_text.strip(),
        ]
    )


def build_dispatch_hook(config: DispatchConfig | None = None) -> DispatchHook:
    """Return a dispatch hook that runs the Agents SDK loop."""
    cfg = config or DispatchConfig()

    async def dispatch(
        supervisor: SessionSupervisor,
        event: AgentEvent,
        session: ChannelSession,
    ) -> None:
        if event.kind != EventKind.CHAT_MESSAGE:
            logger.debug("runtime_dispatch: skipping non-chat event kind=%s session=%s", event.kind.value, session.session_id)
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
            await _maybe_record(cfg.session_factory, run_id=run_id, seq=seq, kind=kind, payload=payload)

        runtime_settings = dict(event.payload.get("settings") or {})
        selected_model = resolve_runtime_model_setting(runtime_settings, cfg.model)

        if cfg.session_factory is not None:
            try:
                async with cfg.session_factory() as sess:
                    await record_run_start(
                        sess,
                        run_id=run_id,
                        owner_uid=session.owner_uid,
                        channel=session.channel,
                        session_id=session.session_id,
                        model=_runtime_model_label(selected_model),
                    )
                    await mark_inbox_dispatched(sess, event_id=event.event_id, run_id=run_id)
            except Exception:  # noqa: BLE001
                logger.exception("record_run_start failed run=%s", run_id)

        # Phase 10: thread the originating ws_session_id through so
        # the WS bridge can target persistence + chat rendering at the
        # tab that fired the message. Without this, a multi-tab user
        # whose tabs share the per-user runtime fan-out would have one
        # tab's reply persisted into another tab's session_id (codex
        # P1 from PR #345 review).
        origin_ws_session_id = (
            event.payload.get("ws_session_id") if isinstance(event.payload, dict) else None
        )
        run_started_payload: dict[str, Any] = {
            "text": text,
            "channel": session.channel,
            "owner_uid": session.owner_uid,
        }
        if isinstance(origin_ws_session_id, str) and origin_ws_session_id:
            run_started_payload["ws_session_id"] = origin_ws_session_id
        await emit("run_started", run_started_payload)
        await emit("user_message", {"text": text})

        tool_ctx = ToolContext(
            session_id=session.session_id,
            owner_uid=session.owner_uid,
            channel=session.channel,
            settings=runtime_settings,
            memory_mode=str(event.payload.get("memory_mode") or "files"),
            is_main_session=True,
        )

        mcp_tools: list[Any] = []
        provider = await _ensure_mcp_provider(supervisor, cfg)
        if provider is not None:
            try:
                mcp_tools = list(await provider.get_tools())
            except Exception:  # noqa: BLE001
                logger.exception("runtime_dispatch: MCP provider failed for %s", session.owner_uid)

        connector_tools: list[Any] = []
        connector_loader = cfg.connector_loader or load_connector_tools
        try:
            connector_tools = list(await connector_loader(session.owner_uid))
        except Exception:  # noqa: BLE001
            logger.exception("runtime_dispatch: connector loader failed for %s", session.owner_uid)

        agent_builder = cfg.build_agent_fn or (lambda s, c: _default_build_agent(s, c, cfg, mcp_tools, connector_tools))
        agent = agent_builder(session, tool_ctx)

        instructions = _instructions_for_meter(agent, cfg)
        run_input = text
        try:
            # Pass exclude_run_id so the current turn's run_started +
            # user_message events (already persisted above) don't get
            # read back as chat_history and double-count the user
            # message — that would inflate the meter and could trigger
            # premature compaction on long prompts.
            prepared_context = await build_prepared_context(
                session_factory=cfg.session_factory,
                session_id=session.session_id,
                owner_uid=session.owner_uid,
                current_text=text,
                instructions=instructions,
                tool_names=_tool_names_for_meter(agent),
                model_context_window=cfg.context_window_tokens,
                threshold_pct=cfg.compact_threshold_pct,
                exclude_run_id=run_id,
            )
            run_input = prepared_context.prompt
            try:
                checkpoint = await maybe_create_checkpoint(
                    session_factory=cfg.session_factory,
                    prepared=prepared_context,
                    owner_uid=session.owner_uid,
                    session_id=session.session_id,
                )
            except Exception:  # noqa: BLE001
                checkpoint = None
                logger.exception("context checkpoint creation failed session=%s", session.session_id)
            if checkpoint is not None:
                # Compaction rewrites the prompt: history + pending tool
                # outputs are dropped and the new checkpoint summary
                # replaces them. Re-derive the meter so the emitted
                # event matches what Runner.run is actually about to
                # see. Fall back to the pre-compaction meter only if
                # the recompute itself fails.
                run_input = _checkpoint_prompt(instructions=instructions, checkpoint=checkpoint, current_text=text)
                try:
                    post_meter = prepared_context.compacted_meter(
                        checkpoint_summary=str(checkpoint.get("summary") or ""),
                    )
                except Exception:  # noqa: BLE001
                    post_meter = prepared_context.meter
                    logger.exception("post-compaction meter recompute failed session=%s", session.session_id)
                await emit("context_meter", post_meter)
                await emit("compaction_checkpoint", {k: v for k, v in checkpoint.items() if k != "summary"})
            else:
                await emit("context_meter", prepared_context.meter)
        except Exception:  # noqa: BLE001
            logger.exception("context meter preparation failed session=%s", session.session_id)

        status = "completed"
        error_text: str | None = None
        try:
            result = await Runner.run(agent, run_input, context=tool_ctx, max_turns=cfg.max_turns)
            for item_record in _summarize_new_items(result.new_items):
                item_type = item_record["type"]
                kind = (
                    "tool_call" if item_type == "tool_call_item"
                    else "tool_result" if item_type == "tool_call_output_item"
                    else "model_message" if item_type == "message_output_item"
                    else "trace"
                )
                await emit(kind, item_record)
                if cfg.session_factory is not None:
                    try:
                        if item_type == "tool_call_item":
                            async with cfg.session_factory() as sess:
                                await record_tool_call_started(
                                    sess,
                                    run_id=run_id,
                                    event_id=event.event_id,
                                    owner_uid=session.owner_uid,
                                    session_id=session.session_id,
                                    tool_name=item_record.get("name") or "unknown",
                                    arguments=item_record.get("arguments"),
                                    call_id=item_record.get("call_id"),
                                )
                        elif item_type == "tool_call_output_item":
                            async with cfg.session_factory() as sess:
                                await record_tool_call_completed(
                                    sess,
                                    run_id=run_id,
                                    call_id=item_record.get("call_id"),
                                    output_preview=item_record.get("output"),
                                )
                    except Exception:  # noqa: BLE001
                        logger.exception("tool-call checkpoint failed run=%s item=%s", run_id, item_type)
            final_text = str(result.final_output) if result.final_output is not None else ""
            final_payload: dict[str, Any] = {"text": final_text}
            if isinstance(origin_ws_session_id, str) and origin_ws_session_id:
                final_payload["ws_session_id"] = origin_ws_session_id
            await emit("final_message", final_payload)
            # Always-on persistence hook. Runs after the fan-out
            # publish above, so when a websocket bridge is attached
            # it has already had its turn to call _log_web_message
            # and mark this run_id in the dedupe LRU. The persister
            # checks the same LRU and skips if already done — but
            # for the no-websocket case (heartbeat, scheduled
            # automation, agent restart with queued events) this is
            # the only thing that lands the assistant reply in the
            # chat-session row.
            persister = cfg.chat_message_persister
            if (
                persister is not None
                and isinstance(origin_ws_session_id, str)
                and origin_ws_session_id
                and final_text.strip()
                and session.owner_uid
            ):
                try:
                    metadata: dict[str, Any] = {
                        "source": "runtime",
                        "action": "final_message",
                        "run_id": run_id,
                        "runtime_session_id": session.session_id,
                        "origin_ws_session_id": origin_ws_session_id,
                    }
                    extra_source = (
                        event.payload.get("source")
                        if isinstance(event.payload, dict)
                        else None
                    )
                    if isinstance(extra_source, str) and extra_source:
                        metadata["trigger_source"] = extra_source
                    await persister(
                        run_id,
                        session.owner_uid,
                        origin_ws_session_id,
                        final_text,
                        metadata,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "chat_message_persister failed run=%s session=%s",
                        run_id,
                        session.session_id,
                    )
        except Exception as exc:  # noqa: BLE001
            # Critical: do NOT re-raise. The supervisor worker serves
            # every channel session for this user — propagating the
            # exception would degrade the entire per-user loop. We
            # fully own the error here: record it on the run row,
            # stream it to subscribers, finalize via the
            # ``finally`` block, and let the worker pick up the next
            # event.
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
                        await finalize_run_and_inbox(sess, run_id=run_id, event_id=event.event_id, run_status=status, error=error_text)
                except Exception:  # noqa: BLE001
                    logger.exception("finalize_run_and_inbox failed run=%s", run_id)

    return dispatch


def install_supervisor_dispatch(registry: SupervisorRegistry, config: DispatchConfig | None = None) -> DispatchHook:
    """Wire the Agents SDK dispatch hook onto every supervisor in registry."""
    hook = build_dispatch_hook(config)
    registry._dispatch = hook  # type: ignore[attr-defined]
    for supervisor in registry._supervisors.values():  # type: ignore[attr-defined]
        supervisor.install_dispatch(hook)
    return hook


__all__ = [
    "ConnectorLoader",
    "DEFAULT_MODEL_ENV",
    "DEFAULT_MODEL_FALLBACK",
    "DispatchConfig",
    "build_agent",
    "build_dispatch_hook",
    "install_supervisor_dispatch",
    "normalize_runtime_model",
    "resolve_runtime_model_setting",
]
