"""Brave Search API integration."""

from __future__ import annotations

from typing import Any

import httpx

from integrations.base import BaseIntegration, IntegrationError
from integrations.models import IntegrationRecord, ToolDefinition, ToolExecutionResult


class BraveSearchIntegration(BaseIntegration):
    """Brave search integration using subscription token header."""

    kind = "brave-search"
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    async def connect(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        api_key = secrets.get("api_key", "")
        if not api_key:
            raise IntegrationError("Brave Search API key is required")
        test = await self._search(api_key, "Aegis UI navigator", 1)
        return {"connected": True, "sample_result_count": len(test.get("results", []))}

    async def disconnect(self, record: IntegrationRecord) -> None:
        return None

    async def health_check(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        api_key = secrets.get("api_key", "")
        result = await self._search(api_key, "health check", 1)
        return {"ok": True, "results": len(result.get("results", []))}

    def list_tools(self) -> list[ToolDefinition]:
        return [ToolDefinition("brave.web_search", "Run Brave web search", {"q": {"type": "string"}})]

    async def _search(self, api_key: str, query: str, count: int, **kwargs: Any) -> dict[str, Any]:
        headers = {"X-Subscription-Token": api_key}
        params = {"q": query, "count": count} | kwargs
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(self.endpoint, headers=headers, params=params)
        response.raise_for_status()
        body = response.json().get("web", {})
        return {"results": body.get("results", [])}

    async def execute_tool(
        self,
        record: IntegrationRecord,
        secrets: dict[str, str],
        tool_name: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        api_key = secrets.get("api_key", "")
        try:
            if tool_name != "brave.web_search":
                raise IntegrationError(f"Unsupported Brave tool: {tool_name}")
            data = await self._search(
                api_key,
                str(params.get("q", "")),
                int(params.get("count", 5)),
                country=params.get("country"),
                search_lang=params.get("search_lang"),
                extra_snippets=params.get("extra_snippets"),
            )
            return ToolExecutionResult(ok=True, tool=tool_name, data=data)
        except (IntegrationError, httpx.HTTPError) as exc:
            return ToolExecutionResult(ok=False, tool=tool_name, error=str(exc))
