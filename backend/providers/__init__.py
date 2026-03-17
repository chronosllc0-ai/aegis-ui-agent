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
        "default_model": "gpt-4.1",
    },
    "anthropic": {
        "module": "backend.providers.anthropic_provider",
        "class": "AnthropicProvider",
        "display_name": "Anthropic",
        "key_prefix": "sk-ant-",
        "default_model": "claude-sonnet-4-20250514",
    },
    "google": {
        "module": "backend.providers.google_provider",
        "class": "GoogleProvider",
        "display_name": "Google (Gemini)",
        "key_prefix": "",
        "default_model": "gemini-2.5-pro",
    },
    "mistral": {
        "module": "backend.providers.mistral_provider",
        "class": "MistralProvider",
        "display_name": "Mistral AI",
        "key_prefix": "",
        "default_model": "mistral-large-latest",
    },
    "groq": {
        "module": "backend.providers.groq_provider",
        "class": "GroqProvider",
        "display_name": "Groq",
        "key_prefix": "gsk_",
        "default_model": "llama-3.3-70b-versatile",
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
        One of ``openai``, ``anthropic``, ``google``, ``mistral``, ``groq``.
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
