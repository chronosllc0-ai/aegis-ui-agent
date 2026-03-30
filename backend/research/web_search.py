"""Web search client wrappers for deep research sessions."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from config import settings

logger = logging.getLogger(__name__)
SEARCH_PROVIDER = getattr(settings, "SEARCH_PROVIDER", "brave")
SEARCH_API_KEY = getattr(settings, "SEARCH_API_KEY", "")


@dataclass
class SearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str
    source_name: str = ""
    published_date: str | None = None


async def web_search(query: str, num_results: int = 10) -> list[SearchResult]:
    if not SEARCH_API_KEY:
        logger.warning("No SEARCH_API_KEY configured — web search disabled")
        return []
    if SEARCH_PROVIDER == "brave":
        return await _brave_search(query, num_results)
    if SEARCH_PROVIDER == "serpapi":
        return await _serpapi_search(query, num_results)
    return []


async def _brave_search(query: str, num_results: int = 10) -> list[SearchResult]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": SEARCH_API_KEY, "Accept": "application/json"},
                params={"q": query, "count": num_results},
            )
            response.raise_for_status()
            data = response.json()
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
                source_name=item.get("meta_url", {}).get("hostname", ""),
                published_date=item.get("age"),
            )
            for item in data.get("web", {}).get("results", [])
        ]
    except Exception:
        logger.warning("Brave search failed", exc_info=True)
        return []


async def _serpapi_search(query: str, num_results: int = 10) -> list[SearchResult]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://serpapi.com/search",
                params={"q": query, "api_key": SEARCH_API_KEY, "num": num_results, "engine": "google"},
            )
            response.raise_for_status()
            data = response.json()
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                source_name=item.get("displayed_link", ""),
                published_date=item.get("date"),
            )
            for item in data.get("organic_results", [])
        ]
    except Exception:
        logger.warning("SerpAPI search failed", exc_info=True)
        return []
