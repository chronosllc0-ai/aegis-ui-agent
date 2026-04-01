"""Fireworks AI provider adapter — OpenAI-compatible API with separate client."""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator

from .base import BaseProvider, ChatMessage, ChatResponse, ProviderCapabilities, StreamChunk

logger = logging.getLogger(__name__)

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"

FIREWORKS_MODELS = [
    "accounts/fireworks/models/kimi-k2p5-turbo",
    "accounts/fireworks/models/kimi-k2-instruct-0905",
]


class FireworksProvider(BaseProvider):
    """Adapter for the Fireworks AI API.

    Uses a dedicated AsyncOpenAI client pointed at Fireworks' base URL so it
    never conflicts with the standard OpenAI client instance used elsewhere.
    """

    provider_name = "fireworks"

    def __init__(self, api_key: str, default_model: str = "accounts/fireworks/models/kimi-k2p5-turbo") -> None:
        self.api_key = api_key
        self.default_model = default_model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI  # same SDK, different instance
            base_url = os.environ.get("FIREWORKS_BASE_URL", FIREWORKS_BASE_URL)
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=base_url,
            )
        return self._client

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            chat=True,
            streaming=True,
            vision=False,
            function_calling=True,
            reasoning=True,
            max_context_tokens=131_072,
        )

    @property
    def available_models(self) -> list[str]:
        return list(FIREWORKS_MODELS)

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def _normalize_model_name(self, model: str | None) -> str:
        """Normalize common Fireworks model aliases to canonical slugs."""
        candidate = (model or self.default_model).strip()
        if not candidate:
            return self.default_model
        if candidate.startswith("accounts/fireworks/models/"):
            return candidate
        if "/" not in candidate:
            candidate = candidate.replace("kimi-k2.5", "kimi-k2p5")
            return f"accounts/fireworks/models/{candidate}"
        return candidate

    def _fallback_models(self, attempted: str) -> list[str]:
        """Return fallback model IDs for not-found responses."""
        fallbacks = ["accounts/fireworks/models/kimi-k2p5-turbo", "accounts/fireworks/models/kimi-k2-instruct-0905"]
        return [name for name in fallbacks if name != attempted]

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
        model_name = self._normalize_model_name(model)
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=self._build_messages(messages),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            status = getattr(getattr(exc, "status_code", None), "__int__", lambda: None)()
            if status != 404:
                response_obj = getattr(exc, "response", None)
            if status != 404:
                response_obj = getattr(exc, "response", None)
                status = getattr(response_obj, "status_code", None)
            if status == 404:
                for fallback in self._fallback_models(model_name):
                    try:
                        logger.warning("Fireworks model %s not found; retrying with %s", model_name, fallback)
                        response = await client.chat.completions.create(
                            model=fallback,
                            messages=self._build_messages(messages),
                            temperature=temperature,
                            max_tokens=max_tokens,
                        )
                        model_name = fallback
                        break
                    except Exception:  # noqa: BLE001
                        continue
                else:
                    raise
            else:
                raise
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
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()
        model_name = self._normalize_model_name(model)

        create_params: dict[str, Any] = {
            "model": model_name,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        response = await client.chat.completions.create(**create_params)
        async for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield StreamChunk(delta=delta.content, finish_reason=chunk.choices[0].finish_reason)
                elif delta:
                    yield StreamChunk(delta="", finish_reason=chunk.choices[0].finish_reason)

    def validate_api_key(self, api_key: str) -> bool:
        return bool(api_key)
