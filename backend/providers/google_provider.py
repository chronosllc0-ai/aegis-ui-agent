"""Google Gemini provider adapter."""

from __future__ import annotations

import base64
import logging
from typing import Any, AsyncIterator

from .base import BaseProvider, ChatMessage, ChatResponse, ProviderCapabilities, StreamChunk

logger = logging.getLogger(__name__)

GOOGLE_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]


class GoogleProvider(BaseProvider):
    """Adapter for the Google Gemini / GenAI API."""

    provider_name = "google"

    def __init__(self, api_key: str, default_model: str = "gemini-2.5-pro") -> None:
        self.api_key = api_key
        self.default_model = default_model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            chat=True,
            streaming=True,
            vision=True,
            function_calling=True,
            max_context_tokens=1_000_000,
        )

    @property
    def available_models(self) -> list[str]:
        return list(GOOGLE_MODELS)

    def _build_contents(self, messages: list[ChatMessage]) -> tuple[str | None, list[dict[str, Any]]]:
        """Build Gemini-format contents and extract system instruction."""
        system: str | None = None
        contents: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "system":
                system = msg.content
                continue
            parts: list[dict[str, Any]] = [{"text": msg.content}]
            for img in msg.images:
                b64 = base64.b64encode(img).decode()
                parts.append({"inline_data": {"mime_type": "image/png", "data": b64}})
            role = "model" if msg.role == "assistant" else "user"
            contents.append({"role": role, "parts": parts})
        return system, contents

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
        system, contents = self._build_contents(messages)
        config: dict[str, Any] = {"temperature": temperature, "max_output_tokens": max_tokens}
        if system:
            config["system_instruction"] = system
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )
        text = response.text or ""
        usage = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            um = response.usage_metadata
            usage = {
                "prompt_tokens": getattr(um, "prompt_token_count", 0),
                "completion_tokens": getattr(um, "candidates_token_count", 0),
                "total_tokens": getattr(um, "total_token_count", 0),
            }
        return ChatResponse(
            content=text,
            model=model_name,
            provider=self.provider_name,
            usage=usage,
            finish_reason="stop",
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
        system, contents = self._build_contents(messages)
        config: dict[str, Any] = {"temperature": temperature, "max_output_tokens": max_tokens}
        if system:
            config["system_instruction"] = system
        async for chunk in client.aio.models.generate_content_stream(
            model=model_name,
            contents=contents,
            config=config,
        ):
            text = chunk.text or ""
            if text:
                yield StreamChunk(delta=text)

    def validate_api_key(self, api_key: str) -> bool:
        return bool(api_key and len(api_key) > 10)
