"""Linear OAuth2 connector — issues, projects, cycles, teams."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.connectors.base import BaseConnector, ConnectorAction, OAuthTokens

logger = logging.getLogger(__name__)

_LINEAR_API = "https://api.linear.app/graphql"


class LinearConnector(BaseConnector):
    connector_id = "linear"
    display_name = "Linear"
    oauth_authorize_url = "https://linear.app/oauth/authorize"
    oauth_token_url = "https://api.linear.app/oauth/token"
    default_scopes = ["read", "write", "issues:create", "comments:create"]

    def get_authorize_url(self, redirect_uri: str, state: str, scopes: list[str] | None = None) -> str:
        from urllib.parse import urlencode
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": ",".join(scopes or self.default_scopes),
            "prompt": "consent",
        }
        return f"{self.oauth_authorize_url}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.oauth_token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return OAuthTokens(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in"),
            scope=data.get("scope", ""),
            raw=data,
        )

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        # Linear access tokens are long-lived; refresh not typically needed
        return OAuthTokens(access_token=refresh_token)

    async def revoke(self, access_token: str) -> bool:
        # Linear: user revokes from settings; no programmatic revoke
        return True

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        query = "{ viewer { id name email } }"
        data = await _graphql(access_token, query)
        return data.get("data", {}).get("viewer", {})

    def list_actions(self) -> list[ConnectorAction]:
        return [
            ConnectorAction(id="list_issues", name="List Issues", description="List issues assigned to you or in a team", parameters={"team_key": "string (optional)"}, category="issues"),
            ConnectorAction(id="get_issue", name="Get Issue", description="Get issue details by identifier", parameters={"identifier": "string"}, category="issues"),
            ConnectorAction(id="create_issue", name="Create Issue", description="Create a new issue", parameters={"team_id": "string", "title": "string", "description": "string (optional)", "priority": "int (optional)"}, category="issues"),
            ConnectorAction(id="update_issue", name="Update Issue", description="Update an issue's state or fields", parameters={"issue_id": "string", "state_id": "string (optional)", "title": "string (optional)"}, category="issues"),
            ConnectorAction(id="list_projects", name="List Projects", description="List all projects", category="projects"),
            ConnectorAction(id="list_teams", name="List Teams", description="List all teams in the workspace", category="teams"),
            ConnectorAction(id="search_issues", name="Search Issues", description="Search issues by text", parameters={"query": "string"}, category="search"),
        ]

    async def execute_action(self, action_id: str, params: dict[str, Any], access_token: str) -> dict[str, Any]:
        if action_id == "list_issues":
            return await _list_issues(access_token, params)
        elif action_id == "get_issue":
            return await _get_issue(access_token, params)
        elif action_id == "create_issue":
            return await _create_issue(access_token, params)
        elif action_id == "update_issue":
            return await _update_issue(access_token, params)
        elif action_id == "list_projects":
            return await _list_projects(access_token)
        elif action_id == "list_teams":
            return await _list_teams(access_token)
        elif action_id == "search_issues":
            return await _search_issues(access_token, params)
        else:
            return {"error": f"Unknown action: {action_id}"}


async def _graphql(token: str, query: str, variables: dict | None = None) -> dict:
    async with httpx.AsyncClient() as client:
        body: dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables
        resp = await client.post(
            _LINEAR_API,
            headers={"Authorization": token, "Content-Type": "application/json"},
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


async def _list_issues(token: str, params: dict) -> dict:
    query = """
    query($first: Int) {
        issues(first: $first, orderBy: updatedAt) {
            nodes {
                id identifier title state { name } priority assignee { name } createdAt updatedAt
            }
        }
    }
    """
    data = await _graphql(token, query, {"first": params.get("limit", 25)})
    nodes = data.get("data", {}).get("issues", {}).get("nodes", [])
    return {"ok": True, "issues": [{"id": n["id"], "identifier": n["identifier"], "title": n["title"], "state": n.get("state", {}).get("name", ""), "priority": n.get("priority"), "assignee": (n.get("assignee") or {}).get("name", ""), "updated_at": n.get("updatedAt")} for n in nodes]}


async def _get_issue(token: str, params: dict) -> dict:
    identifier = params.get("identifier", "")
    if not identifier:
        return {"error": "identifier is required"}
    query = """
    query($id: String!) {
        issue(id: $id) {
            id identifier title description state { name } priority assignee { name } labels { nodes { name } } createdAt updatedAt
        }
    }
    """
    data = await _graphql(token, query, {"id": identifier})
    issue = data.get("data", {}).get("issue")
    if not issue:
        return {"error": "Issue not found"}
    return {"ok": True, "issue": issue}


async def _create_issue(token: str, params: dict) -> dict:
    team_id = params.get("team_id", "")
    title = params.get("title", "")
    if not team_id or not title:
        return {"error": "team_id and title are required"}
    mutation = """
    mutation($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue { id identifier title url }
        }
    }
    """
    input_data: dict[str, Any] = {"teamId": team_id, "title": title}
    if params.get("description"):
        input_data["description"] = params["description"]
    if params.get("priority"):
        input_data["priority"] = params["priority"]
    data = await _graphql(token, mutation, {"input": input_data})
    result = data.get("data", {}).get("issueCreate", {})
    if result.get("success"):
        return {"ok": True, "issue": result.get("issue", {})}
    return {"error": "Failed to create issue"}


async def _update_issue(token: str, params: dict) -> dict:
    issue_id = params.get("issue_id", "")
    if not issue_id:
        return {"error": "issue_id is required"}
    mutation = """
    mutation($id: String!, $input: IssueUpdateInput!) {
        issueUpdate(id: $id, input: $input) {
            success
            issue { id identifier title state { name } }
        }
    }
    """
    input_data: dict[str, Any] = {}
    if params.get("state_id"):
        input_data["stateId"] = params["state_id"]
    if params.get("title"):
        input_data["title"] = params["title"]
    if params.get("description"):
        input_data["description"] = params["description"]
    data = await _graphql(token, mutation, {"id": issue_id, "input": input_data})
    result = data.get("data", {}).get("issueUpdate", {})
    return {"ok": True, "issue": result.get("issue", {})} if result.get("success") else {"error": "Failed to update issue"}


async def _list_projects(token: str) -> dict:
    query = """
    { projects(first: 25) { nodes { id name state startDate targetDate } } }
    """
    data = await _graphql(token, query)
    nodes = data.get("data", {}).get("projects", {}).get("nodes", [])
    return {"ok": True, "projects": nodes}


async def _list_teams(token: str) -> dict:
    query = """
    { teams { nodes { id name key } } }
    """
    data = await _graphql(token, query)
    nodes = data.get("data", {}).get("teams", {}).get("nodes", [])
    return {"ok": True, "teams": nodes}


async def _search_issues(token: str, params: dict) -> dict:
    query_text = params.get("query", "")
    if not query_text:
        return {"error": "query is required"}
    query = """
    query($term: String!) {
        searchIssues(term: $term, first: 20) {
            nodes {
                id identifier title state { name } assignee { name }
            }
        }
    }
    """
    data = await _graphql(token, query, {"term": query_text})
    nodes = data.get("data", {}).get("searchIssues", {}).get("nodes", [])
    return {"ok": True, "issues": nodes}
