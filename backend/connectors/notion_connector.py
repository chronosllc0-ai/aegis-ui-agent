"""Notion OAuth2 connector — pages, databases, blocks, search."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.connectors.base import BaseConnector, ConnectorAction, OAuthTokens

logger = logging.getLogger(__name__)

_NOTION_API = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


class NotionConnector(BaseConnector):
    connector_id = "notion"
    display_name = "Notion"
    oauth_authorize_url = "https://api.notion.com/v1/oauth/authorize"
    oauth_token_url = "https://api.notion.com/v1/oauth/token"
    default_scopes = []  # Notion uses "owner" + integration capabilities, not granular scopes

    def get_authorize_url(self, redirect_uri: str, state: str, scopes: list[str] | None = None) -> str:
        from urllib.parse import urlencode
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "owner": "user",
        }
        return f"{self.oauth_authorize_url}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        import base64
        credentials = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.oauth_token_url,
                json={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
                headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        return OAuthTokens(
            access_token=data["access_token"],
            token_type=data.get("token_type", "bearer"),
            raw=data,
        )

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        # Notion tokens don't expire / refresh via standard flow
        return OAuthTokens(access_token=refresh_token)

    async def revoke(self, access_token: str) -> bool:
        # Notion doesn't have a revoke endpoint; user disconnects from Notion settings
        return True

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_NOTION_API}/users/me", headers=_headers(access_token))
            resp.raise_for_status()
            return resp.json()

    def list_actions(self) -> list[ConnectorAction]:
        return [
            ConnectorAction(id="search", name="Search", description="Search pages and databases", parameters={"query": "string"}, category="search"),
            ConnectorAction(id="list_databases", name="List Databases", description="List all databases the integration can access", category="databases"),
            ConnectorAction(id="query_database", name="Query Database", description="Query a Notion database", parameters={"database_id": "string"}, category="databases"),
            ConnectorAction(id="get_page", name="Get Page", description="Get a page's properties", parameters={"page_id": "string"}, category="pages"),
            ConnectorAction(id="create_page", name="Create Page", description="Create a new page in a database", parameters={"database_id": "string", "properties": "object"}, category="pages"),
            ConnectorAction(id="get_block_children", name="Get Block Children", description="Get content blocks of a page", parameters={"block_id": "string"}, category="blocks"),
        ]

    async def execute_action(self, action_id: str, params: dict[str, Any], access_token: str) -> dict[str, Any]:
        headers = _headers(access_token)
        async with httpx.AsyncClient() as client:
            if action_id == "search":
                return await _search(client, headers, params)
            elif action_id == "list_databases":
                return await _list_databases(client, headers)
            elif action_id == "query_database":
                return await _query_database(client, headers, params)
            elif action_id == "get_page":
                return await _get_page(client, headers, params)
            elif action_id == "create_page":
                return await _create_page(client, headers, params)
            elif action_id == "get_block_children":
                return await _get_blocks(client, headers, params)
            else:
                return {"error": f"Unknown action: {action_id}"}


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Notion-Version": _NOTION_VERSION, "Content-Type": "application/json"}


async def _search(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    query = params.get("query", "")
    body: dict[str, Any] = {"page_size": 20}
    if query:
        body["query"] = query
    resp = await client.post(f"{_NOTION_API}/search", headers=headers, json=body)
    resp.raise_for_status()
    data = resp.json()
    results = []
    for r in data.get("results", []):
        title = ""
        if r.get("object") == "page":
            for prop in r.get("properties", {}).values():
                if prop.get("type") == "title":
                    title = "".join(t.get("plain_text", "") for t in prop.get("title", []))
                    break
        elif r.get("object") == "database":
            title = "".join(t.get("plain_text", "") for t in r.get("title", []))
        results.append({"id": r["id"], "object": r["object"], "title": title, "url": r.get("url", "")})
    return {"ok": True, "results": results}


async def _list_databases(client: httpx.AsyncClient, headers: dict) -> dict:
    resp = await client.post(f"{_NOTION_API}/search", headers=headers, json={"filter": {"property": "object", "value": "database"}, "page_size": 50})
    resp.raise_for_status()
    data = resp.json()
    databases = []
    for db in data.get("results", []):
        title = "".join(t.get("plain_text", "") for t in db.get("title", []))
        databases.append({"id": db["id"], "title": title, "url": db.get("url", "")})
    return {"ok": True, "databases": databases}


async def _query_database(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    database_id = params.get("database_id", "")
    if not database_id:
        return {"error": "database_id is required"}
    body: dict[str, Any] = {"page_size": 20}
    if params.get("filter"):
        body["filter"] = params["filter"]
    resp = await client.post(f"{_NOTION_API}/databases/{database_id}/query", headers=headers, json=body)
    resp.raise_for_status()
    data = resp.json()
    return {"ok": True, "results": data.get("results", []), "has_more": data.get("has_more", False)}


async def _get_page(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    page_id = params.get("page_id", "")
    if not page_id:
        return {"error": "page_id is required"}
    resp = await client.get(f"{_NOTION_API}/pages/{page_id}", headers=headers)
    resp.raise_for_status()
    return {"ok": True, "page": resp.json()}


async def _create_page(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    database_id = params.get("database_id", "")
    properties = params.get("properties", {})
    if not database_id:
        return {"error": "database_id is required"}
    body: dict[str, Any] = {"parent": {"database_id": database_id}, "properties": properties}
    if params.get("children"):
        body["children"] = params["children"]
    resp = await client.post(f"{_NOTION_API}/pages", headers=headers, json=body)
    resp.raise_for_status()
    page = resp.json()
    return {"ok": True, "page_id": page["id"], "url": page.get("url", "")}


async def _get_blocks(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    block_id = params.get("block_id", "")
    if not block_id:
        return {"error": "block_id is required"}
    resp = await client.get(f"{_NOTION_API}/blocks/{block_id}/children", headers=headers, params={"page_size": 100})
    resp.raise_for_status()
    data = resp.json()
    return {"ok": True, "blocks": data.get("results", []), "has_more": data.get("has_more", False)}
