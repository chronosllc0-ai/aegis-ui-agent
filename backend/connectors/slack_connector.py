"""Slack OAuth2 connector — channels, messages, users, files."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.connectors.base import BaseConnector, ConnectorAction, OAuthTokens

logger = logging.getLogger(__name__)

_SLACK_API = "https://slack.com/api"


class SlackOAuthConnector(BaseConnector):
    connector_id = "slack"
    display_name = "Slack"
    oauth_authorize_url = "https://slack.com/oauth/v2/authorize"
    oauth_token_url = "https://slack.com/api/oauth.v2.access"
    default_scopes = [
        # Messaging
        "app_mentions:read",
        "assistant:write",
        "chat:write",
        "chat:write.customize",
        # Channels
        "channels:history",
        "channels:join",
        "channels:read",
        # Groups / DMs
        "groups:history",
        "groups:read",
        "im:history",
        "im:read",
        # Users & reactions
        "emoji:read",
        "reactions:read",
        "reactions:write",
        "users:read",
        # Files & search
        "files:read",
        "files:write",
        # NOTE: search:read.files and search:read.im are NOT valid Slack scopes;
        # the correct scope for search is search:read (user token only).
    ]

    def get_authorize_url(self, redirect_uri: str, state: str, scopes: list[str] | None = None) -> str:
        from urllib.parse import urlencode
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": ",".join(scopes or self.default_scopes),
        }
        # Slack search requires a user token — search:read is a user scope only.
        # "chat:write" is included here for user-token DM capability.
        # "chat:write.public" must NOT appear in user_scope (it's bot-only).
        params["user_scope"] = "search:read,chat:write,emoji:read"
        return f"{self.oauth_authorize_url}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        data = await self._post_token_request({
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        })
        # Slack returns nested: { "ok": true, "access_token": "...", "authed_user": { "access_token": "..." } }
        access_token = data.get("access_token", "")
        user_token = data.get("authed_user", {}).get("access_token", "")
        return OAuthTokens(
            access_token=access_token,
            refresh_token=user_token,  # Store user token as "refresh" for dual use
            token_type="Bearer",
            scope=data.get("scope", ""),
            raw=data,
        )

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        # Slack bot tokens don't expire; for rotation-enabled tokens:
        data = await self._post_token_request({
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        })
        return OAuthTokens(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", refresh_token),
            scope=data.get("scope", ""),
            raw=data,
        )

    async def revoke(self, access_token: str) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{_SLACK_API}/auth.revoke", headers={"Authorization": f"Bearer {access_token}"})
            data = resp.json()
            return data.get("ok", False)

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_SLACK_API}/auth.test", headers={"Authorization": f"Bearer {access_token}"})
            data = resp.json()
            return {"team": data.get("team", ""), "user": data.get("user", ""), "team_id": data.get("team_id", ""), "user_id": data.get("user_id", "")}

    def list_actions(self) -> list[ConnectorAction]:
        return [
            ConnectorAction(id="list_channels", name="List Channels", description="List workspace channels", category="channels"),
            ConnectorAction(id="read_channel", name="Read Channel History", description="Read recent messages from a channel", parameters={"channel": "string"}, category="channels"),
            ConnectorAction(id="send_message", name="Send Message", description="Send a message to a channel", parameters={"channel": "string", "text": "string"}, category="messages"),
            ConnectorAction(id="search_messages", name="Search Messages", description="Search workspace messages", parameters={"query": "string"}, category="search"),
            ConnectorAction(id="list_users", name="List Users", description="List workspace members", category="users"),
            ConnectorAction(id="list_files", name="List Files", description="List shared files", category="files"),
        ]

    async def execute_action(self, action_id: str, params: dict[str, Any], access_token: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            if action_id == "list_channels":
                return await _list_channels(client, headers)
            elif action_id == "read_channel":
                return await _read_channel(client, headers, params)
            elif action_id == "send_message":
                return await _send_message(client, headers, params)
            elif action_id == "search_messages":
                return await _search_messages(client, headers, params)
            elif action_id == "list_users":
                return await _list_users(client, headers)
            elif action_id == "list_files":
                return await _list_files(client, headers, params)
            else:
                return {"error": f"Unknown action: {action_id}"}


async def _list_channels(client: httpx.AsyncClient, headers: dict) -> dict:
    resp = await client.get(f"{_SLACK_API}/conversations.list", headers=headers, params={"types": "public_channel,private_channel", "limit": 100})
    data = resp.json()
    if not data.get("ok"):
        return {"error": data.get("error", "API call failed")}
    channels = data.get("channels", [])
    return {"ok": True, "channels": [{"id": c["id"], "name": c["name"], "topic": c.get("topic", {}).get("value", ""), "num_members": c.get("num_members", 0)} for c in channels]}


async def _read_channel(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    channel = params.get("channel", "")
    if not channel:
        return {"error": "channel is required"}
    limit = min(params.get("limit", 20), 100)
    resp = await client.get(f"{_SLACK_API}/conversations.history", headers=headers, params={"channel": channel, "limit": limit})
    data = resp.json()
    if not data.get("ok"):
        return {"error": data.get("error", "API call failed")}
    messages = data.get("messages", [])
    return {"ok": True, "messages": [{"ts": m["ts"], "user": m.get("user", ""), "text": m.get("text", ""), "type": m.get("type", "")} for m in messages]}


async def _send_message(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    channel = params.get("channel", "")
    text = params.get("text", "")
    if not channel or not text:
        return {"error": "channel and text are required"}
    resp = await client.post(f"{_SLACK_API}/chat.postMessage", headers={**headers, "Content-Type": "application/json"}, json={"channel": channel, "text": text})
    data = resp.json()
    if not data.get("ok"):
        return {"error": data.get("error", "Send failed")}
    return {"ok": True, "ts": data.get("ts", ""), "channel": data.get("channel", "")}


async def _search_messages(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    query = params.get("query", "")
    if not query:
        return {"error": "query is required"}
    resp = await client.get(f"{_SLACK_API}/search.messages", headers=headers, params={"query": query, "count": 20})
    data = resp.json()
    if not data.get("ok"):
        return {"error": data.get("error", "Search failed")}
    matches = data.get("messages", {}).get("matches", [])
    return {"ok": True, "messages": [{"text": m.get("text", ""), "channel": m.get("channel", {}).get("name", ""), "user": m.get("username", ""), "ts": m.get("ts", ""), "permalink": m.get("permalink", "")} for m in matches]}


async def _list_users(client: httpx.AsyncClient, headers: dict) -> dict:
    resp = await client.get(f"{_SLACK_API}/users.list", headers=headers, params={"limit": 100})
    data = resp.json()
    if not data.get("ok"):
        return {"error": data.get("error", "API call failed")}
    members = data.get("members", [])
    return {"ok": True, "users": [{"id": m["id"], "name": m.get("name", ""), "real_name": m.get("real_name", ""), "is_admin": m.get("is_admin", False)} for m in members if not m.get("is_bot") and not m.get("deleted")]}


async def _list_files(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    resp = await client.get(f"{_SLACK_API}/files.list", headers=headers, params={"count": 20})
    data = resp.json()
    if not data.get("ok"):
        return {"error": data.get("error", "API call failed")}
    files = data.get("files", [])
    return {"ok": True, "files": [{"id": f["id"], "name": f.get("name", ""), "filetype": f.get("filetype", ""), "size": f.get("size", 0), "url_private": f.get("url_private", ""), "created": f.get("created")} for f in files]}
