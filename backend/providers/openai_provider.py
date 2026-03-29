"""OpenAI provider adapter."""

from __future__ import annotations

import base64
import logging
from typing import Any, AsyncIterator

from .base import BaseProvider, ChatMessage, ChatResponse, ProviderCapabilities, StreamChunk

logger = logging.getLogger(__name__)

OPENAI_MODELS = [
    "gpt-5.2",
    "gpt-5.2-pro",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "o4-mini",
    "o3",
]

OPENAI_REASONING_MODELS = {"o3", "o4-mini"}


class OpenAIProvider(BaseProvider):
    """Adapter for the OpenAI chat completions API."""

    provider_name = "openai"

    def __init__(self, api_key: str, default_model: str = "gpt-5.2") -> None:
        self.api_key = api_key
        self.default_model = default_model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            chat=True,
            streaming=True,
            vision=True,
            function_calling=True,
            reasoning=True,
            max_context_tokens=128_000,
        )

    @property
    def available_models(self) -> list[str]:
        return list(OPENAI_MODELS)

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Convert unified messages to OpenAI format."""
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.images:
                content: list[dict[str, Any]] = [{"type": "text", "text": msg.content}]
                for img in msg.images:
                    b64 = base64.b64encode(img).decode()
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    })
                result.append({"role": msg.role, "content": content})
            else:
                result.append({"role": msg.role, "content": msg.content})
        return result

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
            **kwargs,
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

        # o-series models use reasoning_effort instead of temperature
        params: dict[str, Any] = {
            "model": model_name,
            "messages": self._build_messages(messages),
            "max_tokens": max_tokens,
            "stream": True,
        }
        if model_name in OPENAI_REASONING_MODELS and enable_reasoning:
            params["reasoning_effort"] = reasoning_effort
        else:
            params["temperature"] = temperature

        response = await client.chat.completions.create(**params)
        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield StreamChunk(delta=delta.content, finish_reason=chunk.choices[0].finish_reason)
            elif delta:
                yield StreamChunk(delta="", finish_reason=chunk.choices[0].finish_reason)

    def validate_api_key(self, api_key: str) -> bool:
        return bool(api_key and api_key.startswith("sk-"))
