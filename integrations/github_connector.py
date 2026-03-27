"""GitHub App webhook integration client."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GitHubIntegration(BaseIntegration):
    """GitHub App connector with real API calls."""

    name = "github"

    def __init__(self) -> None:
        self.connected = False
        self._token: str | None = None
        self._webhook_secret: str | None = None
        self._app_id: str | None = None
        self._username: str | None = None

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate the token by calling /user and store metadata."""
        token = str(config.get("token", "")).strip()
        webhook_secret = str(config.get("webhook_secret", "")).strip()
        app_id = str(config.get("app_id", "")).strip()
        self._token = token or None
        self._webhook_secret = webhook_secret or None
        self._app_id = app_id or None

        if not self._token:
            self.connected = False
            return {"connected": False, "username": None, "error": "Missing token"}

        try:
            data = await self._request("GET", "/user")
        except Exception as exc:  # noqa: BLE001
            logger.warning("GitHub auth failed: %s", exc)
            self.connected = False
            return {"connected": False, "username": None, "error": str(exc)}

        if isinstance(data, dict) and "login" in data:
            self.connected = True
            self._username = str(data["login"])
            return {"connected": True, "username": self._username}

        self.connected = False
        if isinstance(data, dict):
            return {"connected": False, "username": None, "error": data.get("message") or "Auth failed"}
        return {"connected": False, "username": None, "error": "Auth failed"}

    def verify_webhook_signature(self, payload_body: bytes, signature_header: str) -> bool:
        """Verify GitHub webhook HMAC-SHA256 signature."""
        if not self._webhook_secret or not signature_header:
            return False
        expected = "sha256=" + hmac.new(
            self._webhook_secret.encode(),
            payload_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header)

    async def disconnect(self) -> None:
        """Disconnect and clear all auth/session data."""
        self.connected = False
        self._token = None
        self._webhook_secret = None
        self._app_id = None
        self._username = None

    def list_tools(self) -> list[dict[str, Any]]:
        """Return tools this integration supports."""
        return [
            {"name": "github_list_repos", "description": "List repositories for the authenticated user"},
            {"name": "github_get_issues", "description": "Get issues for a repository"},
            {"name": "github_create_issue", "description": "Create a new issue"},
            {"name": "github_get_pull_requests", "description": "List pull requests for a repo"},
            {"name": "github_create_comment", "description": "Comment on an issue or PR"},
            {"name": "github_get_file", "description": "Get file content from a repo"},
            {"name": "github_webhook_event", "description": "Process incoming webhook event"},
        ]

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Dispatch GitHub tool execution."""
        if not self.connected or not self._token:
            return {"ok": False, "tool": tool_name, "error": "GitHub integration is not connected"}

        if tool_name == "github_list_repos":
            return await self._list_repos(params)
        if tool_name == "github_get_issues":
            return await self._get_issues(params)
        if tool_name == "github_create_issue":
            return await self._create_issue(params)
        if tool_name == "github_get_pull_requests":
            return await self._get_pull_requests(params)
        if tool_name == "github_create_comment":
            return await self._create_comment(params)
        if tool_name == "github_get_file":
            return await self._get_file(params)

        return {"ok": False, "tool": tool_name, "error": "Unsupported tool"}

    async def _list_repos(self, params: dict[str, Any]) -> dict[str, Any]:
        per_page = int(params.get("per_page", 30))
        data = await self._request("GET", "/user/repos", params={"per_page": per_page, "sort": "updated"})
        return {"ok": isinstance(data, list), "tool": "github_list_repos", "result": data}

    async def _get_issues(self, params: dict[str, Any]) -> dict[str, Any]:
        repo = str(params.get("repo", "")).strip()
        if not repo:
            return {"ok": False, "tool": "github_get_issues", "error": "repo is required (owner/repo)"}
        state = str(params.get("state", "open"))
        data = await self._request("GET", f"/repos/{repo}/issues", params={"state": state, "per_page": 30})
        return {"ok": isinstance(data, list), "tool": "github_get_issues", "result": data}

    async def _create_issue(self, params: dict[str, Any]) -> dict[str, Any]:
        repo = str(params.get("repo", "")).strip()
        title = str(params.get("title", "")).strip()
        body = str(params.get("body", "")).strip()
        if not repo or not title:
            return {"ok": False, "tool": "github_create_issue", "error": "repo and title are required"}
        data = await self._request("POST", f"/repos/{repo}/issues", json={"title": title, "body": body})
        ok = bool(data.get("id")) if isinstance(data, dict) else False
        return {"ok": ok, "tool": "github_create_issue", "result": data}

    async def _get_pull_requests(self, params: dict[str, Any]) -> dict[str, Any]:
        repo = str(params.get("repo", "")).strip()
        if not repo:
            return {"ok": False, "tool": "github_get_pull_requests", "error": "repo is required"}
        state = str(params.get("state", "open"))
        data = await self._request("GET", f"/repos/{repo}/pulls", params={"state": state, "per_page": 30})
        return {"ok": isinstance(data, list), "tool": "github_get_pull_requests", "result": data}

    async def _create_comment(self, params: dict[str, Any]) -> dict[str, Any]:
        repo = str(params.get("repo", "")).strip()
        issue_number = params.get("issue_number")
        body = str(params.get("body", "")).strip()
        if not repo or issue_number is None or not body:
            return {"ok": False, "tool": "github_create_comment", "error": "repo, issue_number, and body are required"}
        data = await self._request("POST", f"/repos/{repo}/issues/{issue_number}/comments", json={"body": body})
        ok = bool(data.get("id")) if isinstance(data, dict) else False
        return {"ok": ok, "tool": "github_create_comment", "result": data}

    async def _get_file(self, params: dict[str, Any]) -> dict[str, Any]:
        repo = str(params.get("repo", "")).strip()
        path = str(params.get("path", "")).strip()
        ref = str(params.get("ref", "")).strip() or None
        if not repo or not path:
            return {"ok": False, "tool": "github_get_file", "error": "repo and path are required"}
        request_params: dict[str, Any] = {}
        if ref:
            request_params["ref"] = ref
        data = await self._request("GET", f"/repos/{repo}/contents/{path}", params=request_params or None)
        ok = isinstance(data, dict) and "content" in data
        return {"ok": ok, "tool": "github_get_file", "result": data}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        if not self._token:
            return {"message": "Missing token"}

        url = f"{GITHUB_API_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.request(method, url, headers=headers, params=params, json=json)

        try:
            data = response.json()
        except ValueError:
            data = {"message": response.text}

        if response.status_code >= 400:
            error = data.get("message") if isinstance(data, dict) else response.text
            return {"message": error or f"HTTP {response.status_code}", "status": response.status_code}

        return data
