"""Regression tests for Fireworks provider model configuration."""

from __future__ import annotations

from backend.providers import PROVIDER_CATALOGUE
from backend.providers.fireworks_provider import FireworksProvider


def test_fireworks_default_model_is_k2p5() -> None:
    """Provider catalogue should point Fireworks default to the current K2.5 model ID."""
    assert PROVIDER_CATALOGUE["fireworks"]["default_model"] == "accounts/fireworks/models/kimi-k2p5"


def test_fireworks_normalizes_legacy_turbo_alias() -> None:
    """Legacy K2.5 turbo aliases should normalize to the supported K2.5 model ID."""
    provider = FireworksProvider(api_key="test")
    assert provider._normalize_model_name("accounts/fireworks/models/kimi-k2p5-turbo") == "accounts/fireworks/models/kimi-k2p5"
    assert provider._normalize_model_name("kimi-k2p5-turbo") == "accounts/fireworks/models/kimi-k2p5"
