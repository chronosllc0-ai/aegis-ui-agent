"""Base integration interface for MCP-style connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseIntegration(ABC):
    """Common async interface for messaging integrations."""

    name: str

    @abstractmethod
    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        """Connect integration with user-provided config."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect integration."""

    @abstractmethod
    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP-style tool manifest."""

    @abstractmethod
    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call and return structured result."""
