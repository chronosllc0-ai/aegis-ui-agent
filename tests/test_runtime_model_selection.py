from __future__ import annotations

from backend.runtime.agent_loop import (
    DispatchConfig,
    _default_build_agent,
    normalize_runtime_model,
    resolve_runtime_model_setting,
)
from backend.runtime.session import ChannelSession, ChannelSessionKey
from backend.runtime.tools.context import ToolContext


def test_fireworks_ui_selection_maps_to_litellm_provider_prefix() -> None:
    assert (
        normalize_runtime_model("fireworks", "accounts/fireworks/models/kimi-k2p5")
        == "fireworks_ai/accounts/fireworks/models/kimi-k2p5"
    )


def test_chronos_gateway_selection_maps_to_openrouter_prefix() -> None:
    assert (
        normalize_runtime_model("chronos", "nvidia/nemotron-3-super-120b-a12b:free")
        == "openrouter/nvidia/nemotron-3-super-120b-a12b:free"
    )


def test_runtime_settings_override_openai_fallback() -> None:
    assert (
        resolve_runtime_model_setting(
            {"provider": "fireworks", "model": "accounts/fireworks/models/kimi-k2p5"},
            "openai/gpt-5",
        )
        == "fireworks_ai/accounts/fireworks/models/kimi-k2p5"
    )


def test_missing_runtime_settings_preserve_static_fallback() -> None:
    assert resolve_runtime_model_setting({}, "openai/gpt-5") == "openai/gpt-5"


def test_default_agent_builder_uses_per_event_provider_model_settings() -> None:
    session = ChannelSession(ChannelSessionKey(owner_uid="user-1", channel="web"))
    ctx = ToolContext(
        session_id=session.session_id,
        owner_uid=session.owner_uid,
        channel=session.channel,
        settings={"provider": "fireworks", "model": "accounts/fireworks/models/kimi-k2p5"},
        memory_mode="files",
        is_main_session=True,
    )

    agent = _default_build_agent(session, ctx, DispatchConfig(model="openai/gpt-5"))

    assert getattr(agent.model, "model", None) == "fireworks_ai/accounts/fireworks/models/kimi-k2p5"
