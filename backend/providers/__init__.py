"""Multi-model provider registry.

Import :func:`get_provider` to obtain a configured provider instance,
or :func:`list_providers` to enumerate supported backends.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseProvider, ChatMessage, ChatResponse, ProviderCapabilities, StreamChunk

logger = logging.getLogger(__name__)

# ── provider catalogue ────────────────────────────────────────────────
PROVIDER_CATALOGUE: dict[str, dict[str, Any]] = {
    "openai": {
        "module": "backend.providers.openai_provider",
        "class": "OpenAIProvider",
        "display_name": "OpenAI",
        "key_prefix": "sk-",
        "default_model": "gpt-5.2",
    },
    "anthropic": {
        "module": "backend.providers.anthropic_provider",
        "class": "AnthropicProvider",
        "display_name": "Anthropic",
        "key_prefix": "sk-ant-",
        "default_model": "claude-opus-4-6",
    },
    "google": {
        "module": "backend.providers.google_provider",
        "class": "GoogleProvider",
        "display_name": "Google (Gemini)",
        "key_prefix": "",
        "default_model": "gemini-2.5-pro",
    },
    "xai": {
        "module": "backend.providers.xai_provider",
        "class": "XAIProvider",
        "display_name": "xAI",
        "key_prefix": "xai-",
        "default_model": "grok-4-20250720",
    },
    "openrouter": {
        "module": "backend.providers.openrouter_provider",
        "class": "OpenRouterProvider",
        "display_name": "OpenRouter",
        "key_prefix": "sk-or-",
        "default_model": "openai/gpt-5.4",
    },
    "fireworks": {
        "module": "backend.providers.fireworks_provider",
        "class": "FireworksProvider",
        "display_name": "Fireworks AI",
        "key_prefix": "",
        "default_model": "accounts/fireworks/models/kimi-k2p5",
    },
}


def _import_provider_class(provider_name: str) -> type[BaseProvider]:
    """Dynamically import and return the provider class."""
    import importlib

    info = PROVIDER_CATALOGUE.get(provider_name)
    if not info:
        raise ValueError(f"Unknown provider: {provider_name}")
    module = importlib.import_module(info["module"])
    return getattr(module, info["class"])


def get_provider(provider_name: str, api_key: str, **kwargs: Any) -> BaseProvider:
    """Instantiate a provider adapter by name.

    Parameters
    ----------
    provider_name:
        One of ``openai``, ``anthropic``, ``google``, ``xai``, ``openrouter``.
    api_key:
        The API key for the chosen provider.
    **kwargs:
        Additional keyword arguments forwarded to the provider constructor
        (e.g. ``default_model``).
    """
    cls = _import_provider_class(provider_name)
    info = PROVIDER_CATALOGUE[provider_name]
    if "default_model" not in kwargs:
        kwargs["default_model"] = info["default_model"]
    return cls(api_key=api_key, **kwargs)


def list_providers() -> list[dict[str, Any]]:
    """Return metadata for every registered provider."""
    result: list[dict[str, Any]] = []
    for name, info in PROVIDER_CATALOGUE.items():
        cls = _import_provider_class(name)
        instance = cls.__new__(cls)
        result.append({
            "id": name,
            "display_name": info["display_name"],
            "default_model": info["default_model"],
            "models": instance.available_models,
            "capabilities": {
                "vision": instance.capabilities.vision,
                "streaming": instance.capabilities.streaming,
                "function_calling": instance.capabilities.function_calling,
            },
        })
    return result


__all__ = [
    "BaseProvider",
    "ChatMessage",
    "ChatResponse",
    "ProviderCapabilities",
    "StreamChunk",
    "get_provider",
    "list_providers",
    "PROVIDER_CATALOGUE",
]
