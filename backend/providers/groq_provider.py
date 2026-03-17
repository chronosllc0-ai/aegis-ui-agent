"""Groq provider adapter."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from .base import BaseProvider, ChatMessage, ChatResponse, ProviderCapabilities, StreamChunk

logger = logging.getLogger(__name__)

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
    "deepseek-r1-distill-llama-70b",
]


class GroqProvider(BaseProvider):
    """Adapter for the Groq inference API (OpenAI-compatible)."""

    provider_name = "groq"

    def __init__(self, api_key: str, default_model: str = "llama-3.3-70b-versatile") -> None:
        self.api_key = api_key
        self.default_model = default_model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self.api_key)
        return self._client

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            chat=True,
            streaming=True,
            vision=False,
            function_calling=True,
            max_context_tokens=32_768,
        )

    @property
    def available_models(self) -> list[str]:
        return list(GROQ_MODELS)

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> ChatResponse:
        client = self._get_client()
        model_name = model or self.default_model
        response = await client.chat.completions.create(
            model=model_name,
            messages=self._build_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        return ChatResponse(
            content=choice.message.content or "",
            model=model_name,
            provider=self.provider_name,
            usage=usage,
            finish_reason=choice.finish_reason or "stop",
            raw=response,
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()
        model_name = model or self.default_model
        response = await client.chat.completions.create(
            model=model_name,
            messages=self._build_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield StreamChunk(delta=delta.content, finish_reason=chunk.choices[0].finish_reason)

    def validate_api_key(self, api_key: str) -> bool:
        return bool(api_key and api_key.startswith("gsk_"))
