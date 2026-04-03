"""Anthropic provider adapter."""

from __future__ import annotations

import base64
import logging
from typing import Any, AsyncIterator

from .base import BaseProvider, ChatMessage, ChatResponse, ProviderCapabilities, StreamChunk

logger = logging.getLogger(__name__)

ANTHROPIC_MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-sonnet-4-20250514",
    "claude-3.5-sonnet-20241022",
]

ANTHROPIC_REASONING_MODELS = {
    "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5", "claude-sonnet-4-20250514"
}


class AnthropicProvider(BaseProvider):
    """Adapter for the Anthropic Messages API."""

    provider_name = "anthropic"

    def __init__(self, api_key: str, default_model: str = "claude-opus-4-6") -> None:
        self.api_key = api_key
        self.default_model = default_model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            chat=True,
            streaming=True,
            vision=True,
            function_calling=True,
            reasoning=True,
            max_context_tokens=1_000_000,
        )

    @property
    def available_models(self) -> list[str]:
        return list(ANTHROPIC_MODELS)

    def _build_messages(self, messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, Any]]]:
        """Split system message and convert the rest to Anthropic format."""
        system: str | None = None
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "system":
                system = msg.content
                continue
            if msg.images:
                content: list[dict[str, Any]] = []
                for img in msg.images:
                    b64 = base64.b64encode(img).decode()
                    content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": b64},
                    })
                content.append({"type": "text", "text": msg.content})
                result.append({"role": msg.role, "content": content})
            else:
                result.append({"role": msg.role, "content": msg.content})
        return system, result

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
        system, msgs = self._build_messages(messages)
        params: dict[str, Any] = {
            "model": model_name,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            params["system"] = system
        response = await client.messages.create(**params, **kwargs)
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }
        return ChatResponse(
            content=text,
            model=model_name,
            provider=self.provider_name,
            usage=usage,
            finish_reason=response.stop_reason or "end_turn",
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
        reasoning_budget: int = 8000,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()
        model_name = model or self.default_model
        system, msgs = self._build_messages(messages)
        params: dict[str, Any] = {
            "model": model_name,
            "messages": msgs,
            "max_tokens": max_tokens,
        }
        if system:
            params["system"] = system

        if enable_reasoning and model_name in ANTHROPIC_REASONING_MODELS:
            # Extended thinking requires temperature=1 and the interleaved-thinking beta header
            params["thinking"] = {"type": "enabled", "budget_tokens": reasoning_budget}
            params["temperature"] = 1  # required for extended thinking
            try:
                async with client.messages.stream(
                    **params,
                    extra_headers={"anthropic-beta": "interleaved-thinking-2025-05-14"},
                ) as stream_obj:
                    async for event in stream_obj:
                        event_type = getattr(event, "type", "")
                        if event_type == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            delta_type = getattr(delta, "type", "")
                            if delta_type == "thinking_delta":
                                thinking_text = getattr(delta, "thinking", "")
                                if thinking_text:
                                    yield StreamChunk(delta="", reasoning_delta=thinking_text)
                            elif delta_type == "text_delta":
                                text = getattr(delta, "text", "")
                                if text:
                                    yield StreamChunk(delta=text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Extended thinking stream failed, falling back to normal: %s", exc)
                params.pop("thinking", None)
                params["temperature"] = temperature
                async with client.messages.stream(**params) as stream_obj:
                    async for text in stream_obj.text_stream:
                        yield StreamChunk(delta=text)
        else:
            params["temperature"] = temperature
            async with client.messages.stream(**params, **kwargs) as stream_obj:
                async for text in stream_obj.text_stream:
                    yield StreamChunk(delta=text)

    def validate_api_key(self, api_key: str) -> bool:
        return bool(api_key and api_key.startswith("sk-ant-"))
