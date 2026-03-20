"""GitHub OAuth2 connector — repos, issues, pull requests, code search."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.connectors.base import BaseConnector, ConnectorAction, OAuthTokens

logger = logging.getLogger(__name__)

_GH_API = "https://api.github.com"


class GitHubConnector(BaseConnector):
    connector_id = "github"
    display_name = "GitHub"
    oauth_authorize_url = "https://github.com/login/oauth/authorize"
    oauth_token_url = "https://github.com/login/oauth/access_token"
    default_scopes = ["repo", "read:user", "read:org"]

    def get_authorize_url(self, redirect_uri: str, state: str, scopes: list[str] | None = None) -> str:
        return self._build_authorize_url(redirect_uri, state, scopes)

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        data = await self._post_token_request({
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        })
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "bearer"),
            scope=data.get("scope", ""),
            raw=data,
        )

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        # GitHub tokens don't expire by default; if using GitHub Apps with
        # expiring tokens, implement refresh here.
        data = await self._post_token_request({
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        })
        return OAuthTokens(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", refresh_token),
            token_type=data.get("token_type", "bearer"),
            scope=data.get("scope", ""),
            raw=data,
        )

    async def revoke(self, access_token: str) -> bool:
        # GitHub doesn't have a simple revoke endpoint for OAuth tokens.
        # The user can revoke from GitHub settings.
        return True

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_GH_API}/user", headers=_headers(access_token))
            resp.raise_for_status()
            return resp.json()

    def list_actions(self) -> list[ConnectorAction]:
        return [
            ConnectorAction(id="list_repos", name="List Repositories", description="List user's repositories", category="repos"),
            ConnectorAction(id="get_repo", name="Get Repository", description="Get details of a specific repo", parameters={"owner": "string", "repo": "string"}, category="repos"),
            ConnectorAction(id="list_issues", name="List Issues", description="List issues in a repository", parameters={"owner": "string", "repo": "string"}, category="issues"),
            ConnectorAction(id="create_issue", name="Create Issue", description="Create a new issue", parameters={"owner": "string", "repo": "string", "title": "string", "body": "string"}, category="issues"),
            ConnectorAction(id="list_prs", name="List Pull Requests", description="List PRs in a repository", parameters={"owner": "string", "repo": "string"}, category="prs"),
            ConnectorAction(id="get_pr", name="Get Pull Request", description="Get PR details", parameters={"owner": "string", "repo": "string", "number": "int"}, category="prs"),
            ConnectorAction(id="create_pr", name="Create Pull Request", description="Open a new pull request", parameters={"owner": "string", "repo": "string", "title": "string", "body": "string", "head": "string", "base": "string"}, category="prs"),
            ConnectorAction(id="search_code", name="Search Code", description="Search across repositories", parameters={"query": "string"}, category="search"),
            ConnectorAction(id="get_file", name="Get File Contents", description="Read a file from a repo", parameters={"owner": "string", "repo": "string", "path": "string"}, category="repos"),
        ]

    async def execute_action(self, action_id: str, params: dict[str, Any], access_token: str) -> dict[str, Any]:
        headers = _headers(access_token)
        async with httpx.AsyncClient() as client:
            if action_id == "list_repos":
                return await _list_repos(client, headers, params)
            elif action_id == "get_repo":
                return await _get_repo(client, headers, params)
            elif action_id == "list_issues":
                return await _list_issues(client, headers, params)
            elif action_id == "create_issue":
                return await _create_issue(client, headers, params)
            elif action_id == "list_prs":
                return await _list_prs(client, headers, params)
            elif action_id == "get_pr":
                return await _get_pr(client, headers, params)
            elif action_id == "create_pr":
                return await _create_pr(client, headers, params)
            elif action_id == "search_code":
                return await _search_code(client, headers, params)
            elif action_id == "get_file":
                return await _get_file(client, headers, params)
            else:
                return {"error": f"Unknown action: {action_id}"}


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


async def _list_repos(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    sort = params.get("sort", "updated")
    resp = await client.get(f"{_GH_API}/user/repos", headers=headers, params={"sort": sort, "per_page": 30})
    resp.raise_for_status()
    repos = resp.json()
    return {"ok": True, "repos": [{"id": r["id"], "full_name": r["full_name"], "description": r.get("description", ""), "language": r.get("language"), "stars": r.get("stargazers_count", 0), "updated_at": r.get("updated_at"), "html_url": r["html_url"]} for r in repos]}


async def _get_repo(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    owner, repo = params.get("owner", ""), params.get("repo", "")
    if not owner or not repo:
        return {"error": "owner and repo are required"}
    resp = await client.get(f"{_GH_API}/repos/{owner}/{repo}", headers=headers)
    resp.raise_for_status()
    return {"ok": True, "repo": resp.json()}


async def _list_issues(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    owner, repo = params.get("owner", ""), params.get("repo", "")
    if not owner or not repo:
        return {"error": "owner and repo are required"}
    state = params.get("state", "open")
    resp = await client.get(f"{_GH_API}/repos/{owner}/{repo}/issues", headers=headers, params={"state": state, "per_page": 30})
    resp.raise_for_status()
    issues = resp.json()
    return {"ok": True, "issues": [{"number": i["number"], "title": i["title"], "state": i["state"], "user": i.get("user", {}).get("login", ""), "created_at": i.get("created_at"), "labels": [l["name"] for l in i.get("labels", [])]} for i in issues]}


async def _create_issue(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    owner, repo = params.get("owner", ""), params.get("repo", "")
    title = params.get("title", "")
    if not owner or not repo or not title:
        return {"error": "owner, repo, and title are required"}
    body = {"title": title}
    if params.get("body"):
        body["body"] = params["body"]
    if params.get("labels"):
        body["labels"] = params["labels"]
    resp = await client.post(f"{_GH_API}/repos/{owner}/{repo}/issues", headers=headers, json=body)
    resp.raise_for_status()
    issue = resp.json()
    return {"ok": True, "number": issue["number"], "html_url": issue["html_url"]}


async def _list_prs(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    owner, repo = params.get("owner", ""), params.get("repo", "")
    if not owner or not repo:
        return {"error": "owner and repo are required"}
    state = params.get("state", "open")
    resp = await client.get(f"{_GH_API}/repos/{owner}/{repo}/pulls", headers=headers, params={"state": state, "per_page": 30})
    resp.raise_for_status()
    prs = resp.json()
    return {"ok": True, "pull_requests": [{"number": p["number"], "title": p["title"], "state": p["state"], "user": p.get("user", {}).get("login", ""), "head": p.get("head", {}).get("ref", ""), "base": p.get("base", {}).get("ref", ""), "created_at": p.get("created_at")} for p in prs]}


async def _get_pr(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    owner, repo = params.get("owner", ""), params.get("repo", "")
    number = params.get("number")
    if not owner or not repo or not number:
        return {"error": "owner, repo, and number are required"}
    resp = await client.get(f"{_GH_API}/repos/{owner}/{repo}/pulls/{number}", headers=headers)
    resp.raise_for_status()
    return {"ok": True, "pull_request": resp.json()}


async def _create_pr(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    owner, repo = params.get("owner", ""), params.get("repo", "")
    title = params.get("title", "")
    head = params.get("head", "")
    base = params.get("base", "main")
    if not owner or not repo or not title or not head:
        return {"error": "owner, repo, title, and head are required"}
    body = {"title": title, "head": head, "base": base}
    if params.get("body"):
        body["body"] = params["body"]
    resp = await client.post(f"{_GH_API}/repos/{owner}/{repo}/pulls", headers=headers, json=body)
    resp.raise_for_status()
    pr = resp.json()
    return {"ok": True, "number": pr["number"], "html_url": pr["html_url"]}


async def _search_code(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    query = params.get("query", "")
    if not query:
        return {"error": "query is required"}
    resp = await client.get(f"{_GH_API}/search/code", headers=headers, params={"q": query, "per_page": 10})
    resp.raise_for_status()
    data = resp.json()
    return {"ok": True, "total_count": data.get("total_count", 0), "items": [{"name": i["name"], "path": i["path"], "repository": i.get("repository", {}).get("full_name", ""), "html_url": i["html_url"]} for i in data.get("items", [])]}


async def _get_file(client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
    owner, repo = params.get("owner", ""), params.get("repo", "")
    path = params.get("path", "")
    if not owner or not repo or not path:
        return {"error": "owner, repo, and path are required"}
    ref = params.get("ref", "main")
    resp = await client.get(f"{_GH_API}/repos/{owner}/{repo}/contents/{path}", headers=headers, params={"ref": ref})
    resp.raise_for_status()
    data = resp.json()
    content = None
    if data.get("encoding") == "base64" and data.get("content"):
        import base64
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return {"ok": True, "name": data.get("name", ""), "path": data.get("path", ""), "size": data.get("size", 0), "content": content}
