"""Web search helpers for deep research."""

from __future__ import annotations

from typing import Any

import httpx


async def brave_search(query: str, api_key: str, count: int = 8) -> list[dict[str, Any]]:
    """Search Brave web API and return normalized results."""
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": count},
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        )
        resp.raise_for_status()
        data = resp.json()
    results: list[dict[str, Any]] = []
    for item in data.get("web", {}).get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
                "source": "brave",
            }
        )
    return results
