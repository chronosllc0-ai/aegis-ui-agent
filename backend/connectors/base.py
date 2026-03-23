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
        """Read client_id from settings, falling back to DB-stored credentials."""
        from config import settings

        attr = f"{self.connector_id.upper()}_CONNECTOR_CLIENT_ID"
        val = getattr(settings, attr, "")
        if val:
            return val
        return self._get_db_credential("client_id")

    @property
    def _client_secret(self) -> str:
        """Read client_secret from settings, falling back to DB-stored credentials."""
        from config import settings

        attr = f"{self.connector_id.upper()}_CONNECTOR_CLIENT_SECRET"
        val = getattr(settings, attr, "")
        if val:
            return val
        return self._get_db_credential("client_secret")

    def _get_db_credential(self, field: str) -> str:
        """Sync helper to read credential from DB (falls back gracefully)."""
        import asyncio

        async def _fetch() -> str:
            from sqlalchemy import select
            from backend.database import _session_factory, OAuthAppCredential
            from backend.key_management import KeyManager
            from config import settings

            if _session_factory is None:
                return ""
            km = KeyManager(settings.ENCRYPTION_SECRET)
            async with _session_factory() as session:
                row = await session.execute(
                    select(OAuthAppCredential).where(OAuthAppCredential.connector_id == self.connector_id)
                )
                cred = row.scalar_one_or_none()
                if not cred:
                    return ""
                enc = cred.client_id_enc if field == "client_id" else cred.client_secret_enc
                try:
                    return km.decrypt(enc) or ""
                except Exception:
                    return ""

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _fetch())
                    return future.result(timeout=5)
            return loop.run_until_complete(_fetch())
        except Exception:
            return ""
