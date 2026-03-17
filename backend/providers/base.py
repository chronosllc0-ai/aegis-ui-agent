"""Abstract base class for LLM provider adapters."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class ChatMessage:
    """Unified chat message across providers."""

    role: str  # "system" | "user" | "assistant"
    content: str
    images: list[bytes] = field(default_factory=list)
    name: str | None = None


@dataclass
class ChatResponse:
    """Unified chat completion response."""

    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    raw: Any = None


@dataclass
class StreamChunk:
    """Single chunk from a streaming response."""

    delta: str
    finish_reason: str | None = None
    raw: Any = None


@dataclass
class ProviderCapabilities:
    """Declared capabilities of a provider."""

    chat: bool = True
    streaming: bool = True
    vision: bool = False
    function_calling: bool = False
    max_context_tokens: int = 128_000


class BaseProvider(abc.ABC):
    """Abstract base for all LLM provider adapters.

    Each concrete provider must implement ``chat`` and ``stream``.
    Vision support is optional — override ``supports_vision`` and
    include image bytes in :class:`ChatMessage.images`.
    """

    provider_name: str = "base"

    @abc.abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> ChatResponse:
        """Perform a single chat completion."""

    @abc.abstractmethod
    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Yield streaming response chunks."""

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Return provider capability flags."""
        return ProviderCapabilities()

    @property
    def supports_vision(self) -> bool:
        return self.capabilities.vision

    @property
    def available_models(self) -> list[str]:
        """Return the list of supported model identifiers."""
        return []

    def validate_api_key(self, api_key: str) -> bool:
        """Lightweight local validation (format check only)."""
        return bool(api_key and api_key.strip())
