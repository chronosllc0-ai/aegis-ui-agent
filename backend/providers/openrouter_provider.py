"""OpenRouter provider adapter — OpenAI-compatible API."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from .base import BaseProvider, ChatMessage, ChatResponse, ProviderCapabilities, StreamChunk

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

OPENROUTER_MODELS = [
    "openai/gpt-5.4-pro",
    "openai/gpt-5.4",
    "openai/gpt-5.4-mini",
    "openai/gpt-5.4-nano",
    "openai/gpt-5.3-codex",
    "anthropic/claude-opus-4.6",
    "x-ai/grok-4.20-beta",
    "qwen/qwen3-max-thinking",
    "qwen/qwen3-coder-next",
    "qwen/qwen3.5-9b",
    "qwen/qwen3.5-122b-a10b",
    "mistralai/mistral-small-4",
    "google/gemini-3.1-pro-preview",
    "minimax/minimax-m2.7",
    "minimax/minimax-m2.5",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "z-ai/glm-5-turbo",
    "z-ai/glm-5",
    "bytedance-seed/seed-2.0-lite",
    "xiaomi/mimo-v2-omni",
    "xiaomi/mimo-v2-pro",
]


class OpenRouterProvider(BaseProvider):
    """Adapter for the OpenRouter API — proxies 600+ models via OpenAI-compatible endpoint."""

    provider_name = "openrouter"

    def __init__(self, api_key: str, default_model: str = "openai/gpt-5.4") -> None:
        self.api_key = api_key
        self.default_model = default_model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=OPENROUTER_BASE_URL,
                default_headers={
                    "HTTP-Referer": "https://mohex.org",
                    "X-Title": "Aegis",
                },
            )
        return self._client

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            chat=True,
            streaming=True,
            vision=True,
            function_calling=True,
            reasoning=True,
            max_context_tokens=1_048_576,
        )

    @property
    def available_models(self) -> list[str]:
        return list(OPENROUTER_MODELS)

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
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()
        model_name = model or self.default_model

        create_params: dict[str, Any] = {
            "model": model_name,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if enable_reasoning:
            create_params["extra_body"] = {"include_reasoning": True}

        response = await client.chat.completions.create(**create_params)

        # Track if we're inside a <think> block for models that inline reasoning (e.g. Qwen3)
        in_think_block = False

        async for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta:
                    # OpenRouter native reasoning field
                    reasoning_text = getattr(delta, "reasoning", None)
                    if reasoning_text:
                        yield StreamChunk(delta="", reasoning_delta=reasoning_text)

                    if delta.content:
                        text = delta.content
                        # Handle <think>...</think> tags inline (Qwen3 style)
                        while text:
                            if not in_think_block:
                                think_start = text.find("<think>")
                                if think_start == -1:
                                    yield StreamChunk(delta=text)
                                    text = ""
                                else:
                                    # Emit text before <think>
                                    if think_start > 0:
                                        yield StreamChunk(delta=text[:think_start])
                                    text = text[think_start + 7:]
                                    in_think_block = True
                            else:
                                think_end = text.find("</think>")
                                if think_end == -1:
                                    yield StreamChunk(delta="", reasoning_delta=text)
                                    text = ""
                                else:
                                    yield StreamChunk(delta="", reasoning_delta=text[:think_end])
                                    text = text[think_end + 8:]
                                    in_think_block = False

    def validate_api_key(self, api_key: str) -> bool:
        return bool(api_key and api_key.startswith("sk-or-"))
