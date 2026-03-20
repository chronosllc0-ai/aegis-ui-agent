"""OAuth2-based connector framework.

Connectors allow users to link their external accounts (Google, GitHub,
Slack, etc.) so Aegis sub-agents can read/write to their real tools.

Registry
--------
- ``CONNECTOR_CATALOGUE`` — dict of all known connector metadata.
- ``get_connector(connector_id)`` — return the connector class for instantiation.
- ``list_connectors()`` — return metadata list for the frontend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.connectors.base import BaseConnector

# Lazy imports to avoid heavy module loading at startup
_CONNECTOR_CLASSES: dict[str, str] = {
    "google": "backend.connectors.google_connector.GoogleConnector",
    "github": "backend.connectors.github_connector.GitHubConnector",
    "slack": "backend.connectors.slack_connector.SlackOAuthConnector",
    "notion": "backend.connectors.notion_connector.NotionConnector",
    "linear": "backend.connectors.linear_connector.LinearConnector",
}

CONNECTOR_CATALOGUE: dict[str, dict] = {
    "google": {
        "id": "google",
        "name": "Google",
        "description": "Gmail, Google Drive, and Google Calendar",
        "icon": "https://i.postimg.cc/fTSf1B5S/google-icon.png",
        "services": ["Gmail", "Google Drive", "Google Calendar"],
        "scopes_summary": "Read & send email, manage files, view calendar",
        "category": "productivity",
    },
    "github": {
        "id": "github",
        "name": "GitHub",
        "description": "Repositories, issues, pull requests, and code",
        "icon": "https://i.postimg.cc/wT8LSTPN/github-icon.png",
        "services": ["Repos", "Issues", "Pull Requests", "Code Search"],
        "scopes_summary": "Read & write repos, issues, and PRs",
        "category": "development",
    },
    "slack": {
        "id": "slack",
        "name": "Slack",
        "description": "Channels, messages, and workspace data",
        "icon": "https://i.postimg.cc/7Yb8Xk2c/slack-icon.png",
        "services": ["Channels", "Messages", "Users", "Files"],
        "scopes_summary": "Read & send messages, list channels",
        "category": "communication",
    },
    "notion": {
        "id": "notion",
        "name": "Notion",
        "description": "Pages, databases, and workspace content",
        "icon": "https://i.postimg.cc/tgvhXjBf/notion-icon.png",
        "services": ["Pages", "Databases", "Blocks", "Search"],
        "scopes_summary": "Read & edit pages and databases",
        "category": "productivity",
    },
    "linear": {
        "id": "linear",
        "name": "Linear",
        "description": "Issues, projects, and team workflows",
        "icon": "https://i.postimg.cc/g0zZnhqJ/linear-icon.png",
        "services": ["Issues", "Projects", "Cycles", "Teams"],
        "scopes_summary": "Read & manage issues and projects",
        "category": "development",
    },
}


def get_connector(connector_id: str) -> "BaseConnector":
    """Instantiate and return a connector by ID."""
    import importlib

    dotted = _CONNECTOR_CLASSES.get(connector_id)
    if not dotted:
        raise ValueError(f"Unknown connector: {connector_id}")
    module_path, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()


def list_connectors() -> list[dict]:
    """Return the full catalogue for frontend rendering."""
    return list(CONNECTOR_CATALOGUE.values())
