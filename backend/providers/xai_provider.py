"""xAI (Grok) provider adapter — OpenAI-compatible API."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from .base import BaseProvider, ChatMessage, ChatResponse, ProviderCapabilities, StreamChunk

logger = logging.getLogger(__name__)

XAI_BASE_URL = "https://api.x.ai/v1"

XAI_MODELS = [
    "grok-4-20250720",
    "grok-4.20-beta",
    "grok-4.20-multi-agent-beta",
    "grok-3",
    "grok-3-mini",
    "grok-3-mini-fast",
    "grok-2-vision-1212",
]

XAI_REASONING_MODELS = {"grok-3-mini", "grok-3-mini-fast"}


def _normalize_reasoning_effort(effort: str) -> str:
    normalized = (effort or "medium").strip().lower()
    if normalized in {"none", "off", "false", "0"}:
        return "medium"
    if normalized == "minimal":
        return "low"
    if normalized in {"extended", "xhigh", "x-high", "extra_high"}:
        return "high"
    if normalized == "adaptive":
        return "medium"
    return normalized if normalized in {"low", "medium", "high"} else "medium"


class XAIProvider(BaseProvider):
    """Adapter for the xAI (Grok) API — uses OpenAI-compatible endpoint."""

    provider_name = "xai"

    def __init__(self, api_key: str, default_model: str = "grok-4-20250720") -> None:
        self.api_key = api_key
        self.default_model = default_model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key, base_url=XAI_BASE_URL)
        return self._client

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            chat=True,
            streaming=True,
            vision=True,
            function_calling=True,
            reasoning=True,
            max_context_tokens=256_000,
        )

    @property
    def available_models(self) -> list[str]:
        return list(XAI_MODELS)

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
        enable_reasoning: bool = False,
        reasoning_effort: str = "medium",
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()
        model_name = model or self.default_model

        params: dict[str, Any] = {
            "model": model_name,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if model_name in XAI_REASONING_MODELS and enable_reasoning:
            params["reasoning_effort"] = _normalize_reasoning_effort(reasoning_effort)

        response = await client.chat.completions.create(**params)
        async for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta:
                    # xAI returns reasoning tokens in reasoning_content field
                    reasoning_text = getattr(delta, "reasoning_content", None)
                    if reasoning_text:
                        yield StreamChunk(delta="", reasoning_delta=reasoning_text, finish_reason=chunk.choices[0].finish_reason)
                    elif delta.content:
                        yield StreamChunk(delta=delta.content, finish_reason=chunk.choices[0].finish_reason)

    def validate_api_key(self, api_key: str) -> bool:
        return bool(api_key and api_key.startswith("xai-"))
