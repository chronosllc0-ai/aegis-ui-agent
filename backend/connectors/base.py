"""Abstract base class for all OAuth2 connectors.

Every connector implements the standard OAuth2 authorization code flow:
1. ``get_authorize_url()`` — build the provider's consent screen URL
2. ``exchange_code()`` — swap the authorization code for tokens
3. ``refresh_tokens()`` — refresh expired access tokens
4. ``revoke()`` — revoke access and clean up
5. ``execute_action()`` — perform a specific action (read email, create issue, etc.)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OAuthTokens:
    """Token set returned after authorization or refresh."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    scope: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorAction:
    """Describes a single capability a connector exposes."""

    id: str
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    category: str = "general"


class BaseConnector(ABC):
    """OAuth2 connector base class."""

    # Subclasses must define these
    connector_id: str = ""
    display_name: str = ""
    oauth_authorize_url: str = ""
    oauth_token_url: str = ""
    default_scopes: list[str] = []

    @abstractmethod
    def get_authorize_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: list[str] | None = None,
    ) -> str:
        """Return the full OAuth2 authorization URL for browser redirect."""
        ...

    @abstractmethod
    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> OAuthTokens:
        """Exchange an authorization code for access + refresh tokens."""
        ...

    @abstractmethod
    async def refresh_tokens(
        self,
        refresh_token: str,
    ) -> OAuthTokens:
        """Refresh an expired access token."""
        ...

    @abstractmethod
    async def revoke(self, access_token: str) -> bool:
        """Revoke the user's access token. Return True on success."""
        ...

    @abstractmethod
    async def execute_action(
        self,
        action_id: str,
        params: dict[str, Any],
        access_token: str,
    ) -> dict[str, Any]:
        """Execute a connector action (e.g. read_emails, create_issue)."""
        ...

    @abstractmethod
    def list_actions(self) -> list[ConnectorAction]:
        """Return all actions this connector supports."""
        ...

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Fetch basic profile info from the connected account.

        Override in subclasses for provider-specific user endpoints.
        """
        return {}

    def _build_authorize_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: list[str] | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        """Helper to build a standard OAuth2 authorize URL."""
        from urllib.parse import urlencode

        params: dict[str, str] = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": " ".join(scopes or self.default_scopes),
        }
        if extra_params:
            params.update(extra_params)
        return f"{self.oauth_authorize_url}?{urlencode(params)}"

    async def _post_token_request(
        self,
        data: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """POST to the token endpoint and return parsed JSON."""
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.oauth_token_url,
                data=data,
                headers=headers or {"Accept": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    @property
    def _client_id(self) -> str:
        """Read client_id from settings. Override if needed."""
        from config import settings

        attr = f"{self.connector_id.upper()}_CONNECTOR_CLIENT_ID"
        return getattr(settings, attr, "")

    @property
    def _client_secret(self) -> str:
        """Read client_secret from settings. Override if needed."""
        from config import settings

        attr = f"{self.connector_id.upper()}_CONNECTOR_CLIENT_SECRET"
        return getattr(settings, attr, "")
