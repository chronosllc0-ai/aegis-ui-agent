"""Sandboxed code execution helpers for future integration wiring."""

from __future__ import annotations

import os
from typing import Any

from integrations.base import BaseIntegration

BLOCKED_PREFIXES = ("API_", "AWS_", "AZURE_", "GCP_", "SECRET", "TOKEN", "PRIVATE", "CREDENTIAL")


class CodeExecutionIntegration(BaseIntegration):
    """Stubbed code execution integration with safe environment filtering."""

    name = "code-exec"

    def __init__(self) -> None:
        self.connected = False

    def _clean_env(self) -> dict[str, str]:
        """Return a filtered child-process environment map."""
        return {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith(BLOCKED_PREFIXES)
        }

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        self.connected = bool(config.get("enabled", True))
        return {"connected": self.connected}

    async def disconnect(self) -> None:
        self.connected = False

    def list_tools(self) -> list[dict[str, Any]]:
        return [{"name": "code_exec_python", "description": "Execute python snippets"}]

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": self.connected, "tool": tool_name, "params": params, "env_size": len(self._clean_env())}
