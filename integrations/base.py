"""Base integration interfaces and shared helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from time import perf_counter
from typing import Any

from integrations.models import IntegrationRecord, ToolDefinition, ToolExecutionResult


class IntegrationError(RuntimeError):
    """Base exception for user-facing integration failures."""


class RateLimitedError(IntegrationError):
    """Raised when third-party API rate limits a request."""


class BaseIntegration(ABC):
    """Common async interface implemented by all native integrations."""

    kind: str

    @abstractmethod
    async def connect(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        """Validate credentials/config and return connection metadata."""

    @abstractmethod
    async def disconnect(self, record: IntegrationRecord) -> None:
        """Disconnect and clean up integration resources."""

    @abstractmethod
    async def health_check(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        """Return health status metadata for the integration."""

    @abstractmethod
    def list_tools(self) -> list[ToolDefinition]:
        """Return tool manifest available for this integration."""

    @abstractmethod
    async def execute_tool(
        self,
        record: IntegrationRecord,
        secrets: dict[str, str],
        tool_name: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        """Execute integration tool with structured response."""

    async def timed_execute(
        self,
        record: IntegrationRecord,
        secrets: dict[str, str],
        tool_name: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        """Execute tool and annotate latency."""
        start = perf_counter()
        result = await self.execute_tool(record, secrets, tool_name, params)
        result.latency_ms = int((perf_counter() - start) * 1000)
        return result
