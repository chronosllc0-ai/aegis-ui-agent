"""Shared channel adapter contracts for Slack/Discord style integrations."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChannelAdapter(Protocol):
    """Unified async contract for channel-based integrations."""

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]: ...

    async def disconnect(self) -> None: ...

    def list_tools(self) -> list[dict[str, Any]]: ...

    async def send_text(
        self,
        destination: str,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def edit_text(
        self,
        destination: str,
        message_id: str,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def send_file(
        self,
        destination: str,
        file_bytes: bytes,
        *,
        filename: str,
        mime_type: str,
        caption: str | None = None,
    ) -> dict[str, Any]: ...

    async def handle_event(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]: ...
