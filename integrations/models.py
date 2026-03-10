"""Typed models for integration lifecycle, status, and tool execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

IntegrationKind = Literal[
    "telegram",
    "slack",
    "discord",
    "brave-search",
    "filesystem",
    "code-exec",
]

CustomTransport = Literal["streamable_http", "sse", "stdio"]


def utc_now_iso() -> str:
    """Return timezone-aware UTC timestamp in ISO8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IntegrationRecord:
    """Persisted metadata and encrypted credentials for a user integration."""

    user_id: str
    kind: str
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    secret_ref: str | None = None
    status: str = "disabled"
    last_health_check: str | None = None
    last_success_action: str | None = None
    last_error: str | None = None


@dataclass
class ToolDefinition:
    """Schema-like definition for an exposed integration tool."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolExecutionResult:
    """Structured result of a tool execution."""

    ok: bool
    tool: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    latency_ms: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialize tool execution result for API responses."""
        return {
            "ok": self.ok,
            "tool": self.tool,
            "data": self.data,
            "error": self.error,
            "latency_ms": self.latency_ms,
        }


@dataclass
class MCPServerRecord:
    """Persisted metadata for a custom MCP server registration."""

    server_id: str
    user_id: str
    name: str
    transport: CustomTransport
    config: dict[str, Any] = field(default_factory=dict)
    secret_ref: str | None = None
    connected: bool = False
    tool_count: int = 0
    last_test_at: str | None = None
    last_error: str | None = None
