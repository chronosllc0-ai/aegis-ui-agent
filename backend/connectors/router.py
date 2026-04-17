"""API routes for the OAuth2 connector framework.

Handles the full OAuth2 lifecycle:
- ``GET /api/connectors`` — list available connectors + user's connection status
- ``GET /api/connectors/{connector_id}/authorize`` — start OAuth2 flow
- ``GET /api/connectors/callback`` — OAuth2 callback (provider redirects here)
- ``POST /api/connectors/{connector_id}/disconnect`` — revoke + delete connection
- ``POST /api/connectors/{connector_id}/execute`` — run an action on a connected service
- ``GET /api/connectors/{connector_id}/actions`` — list available actions
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.connectors import CONNECTOR_CATALOGUE, get_connector, list_connectors
from backend.database import OAuthPendingState, UserConnection, get_session
from backend.integrations.capability_matrix import resolve_capability_status, unsupported_action_fallback
from backend.key_management import KeyManager
from config import settings

logger = logging.getLogger(__name__)

connector_router = APIRouter(prefix="/api/connectors", tags=["connectors"])

_key_manager = KeyManager(settings.ENCRYPTION_SECRET)


def _get_current_user(request: Request) -> dict[str, Any]:
    """Extract authenticated user from session cookie."""
    from auth import _verify_session

    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload


def _callback_uri() -> str:
    """Build the OAuth2 callback URI."""
    return f"{settings.resolved_public_base_url}/api/connectors/callback"


# ── List connectors + status ──────────────────────────────────────────


@connector_router.get("")
async def list_all_connectors(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List all connectors with the user's connection status."""
    user = _get_current_user(request)
    uid = user["uid"]

    # Fetch user's existing connections
    result = await session.execute(
        select(UserConnection).where(UserConnection.user_id == uid)
    )
    connections = {c.connector_id: c for c in result.scalars().all()}

    catalogue = list_connectors()
    for entry in catalogue:
        conn = connections.get(entry["id"])
        if conn:
            entry["connected"] = True
            entry["status"] = conn.status
            entry["account_email"] = conn.account_email
            entry["account_name"] = conn.account_name
            entry["account_avatar"] = conn.account_avatar
            entry["connected_at"] = conn.connected_at.isoformat() if conn.connected_at else None
        else:
            entry["connected"] = False
            entry["status"] = "not_connected"
            entry["account_email"] = None
            entry["account_name"] = None
            entry["account_avatar"] = None
            entry["connected_at"] = None

        # Check if connector is configured (env var OR DB credentials)
        env_attr = f"{entry['id'].upper()}_CONNECTOR_CLIENT_ID"
        env_configured = bool(getattr(settings, env_attr, ""))
        if not env_configured:
            from backend.database import OAuthAppCredential
            db_cred = await session.execute(
                select(OAuthAppCredential).where(OAuthAppCredential.connector_id == entry["id"])
            )
            entry["configured"] = db_cred.scalar_one_or_none() is not None
        else:
            entry["configured"] = True

    return {"ok": True, "connectors": catalogue}


# ── Slack Events API webhook (challenge verification + event handling) ──


@connector_router.post("/slack/events")
async def slack_events(request: Request) -> JSONResponse:
    """Slack Events API endpoint.

    Handles:
    1. URL verification challenge (type == 'url_verification') — must respond
       with the challenge value so Slack can verify the endpoint.
    2. Event callbacks — process incoming Slack events (future use).
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid json"})

    event_type = body.get("type", "")

    # ── URL verification handshake ──────────────────────────────────────
    if event_type == "url_verification":
        challenge = body.get("challenge", "")
        logger.info("Slack URL verification challenge received")
        return JSONResponse(content={"challenge": challenge})

    # ── Event callback ──────────────────────────────────────────────────
    if event_type == "event_callback":
        event = body.get("event", {})
        logger.info("Slack event received: %s", event.get("type", "unknown"))
        # Acknowledge immediately — process async if needed in future
        return JSONResponse(content={"ok": True})

    # Unknown type — still return 200 so Slack doesn't retry
    logger.warning("Slack events: unknown type=%s", event_type)
    return JSONResponse(content={"ok": True})


# ── Slack Marketplace direct install (unauthenticated 302 → slack.com) ─


@connector_router.get("/slack/install")
async def slack_marketplace_install(request: Request) -> RedirectResponse:
    """Slack Marketplace direct install URL.

    Slack's submission validator makes a GET request here and expects a 302
    redirect to a slack.com OAuth URL.  No user session is required — this
    endpoint is hit by unauthenticated users arriving from the App Directory.
    """
    connector = get_connector("slack")
    state = secrets.token_urlsafe(32)
    # Store state in session for verification on callback (best-effort for
    # unauthenticated requests — session cookie may not persist across redirect,
    # but Slack's validator only checks the 302, not the full flow).
    request.session["oauth_state"] = state
    request.session["oauth_connector"] = "slack"
    url = connector.get_authorize_url(
        redirect_uri=_callback_uri(),
        state=state,
    )
    return RedirectResponse(url=url, status_code=302)


# ── Start OAuth2 flow ─────────────────────────────────────────────────


@connector_router.get("/{connector_id}/authorize")
async def authorize_connector(
    connector_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Generate and return the OAuth2 authorization URL.

    The frontend will redirect the user to this URL.
    """
    user = _get_current_user(request)

    if connector_id not in CONNECTOR_CATALOGUE:
        raise HTTPException(status_code=404, detail=f"Unknown connector: {connector_id}")

    connector = get_connector(connector_id)

    # Generate state token (CSRF protection)
    state = secrets.token_urlsafe(32)

    # Store state in BOTH session cookie AND DB.
    # DB storage is the reliable fallback for providers (like Notion) that redirect
    # through their own domain, which causes SameSite=Lax to block cookie transmission.
    request.session["oauth_state"] = state
    request.session["oauth_connector"] = connector_id

    # Best-effort DB write: if the DB is unavailable, the session cookie is still the
    # primary path and most providers will work fine. Notion (and similar cross-domain
    # redirecters) will fall back to the error flow in that case — preferable to a 500.
    try:
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        pending = OAuthPendingState(
            state_token=state,
            connector_id=connector_id,
            user_id=user.get("uid"),
            expires_at=expires,
        )
        session.add(pending)
        await session.commit()
    except Exception as exc:
        logger.warning("Could not persist OAuth pending state to DB (session-only fallback): %s", exc)
        await session.rollback()

    url = connector.get_authorize_url(
        redirect_uri=_callback_uri(),
        state=state,
    )

    return {"ok": True, "authorize_url": url}


# ── OAuth2 callback ──────────────────────────────────────────────────


@connector_router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Handle the OAuth2 callback from the provider.

    Exchanges the authorization code for tokens, stores them encrypted,
    and redirects the user back to the settings page.
    """
    frontend_url = settings.resolved_frontend_url

    if error:
        logger.warning("OAuth callback error: %s", error)
        return RedirectResponse(f"{frontend_url}/?settings=Connections&connector_error={error}")

    if not code:
        return RedirectResponse(f"{frontend_url}/?settings=Connections&connector_error=no_code")

    # Verify state (CSRF protection).
    # Try session cookie first (fastest path). If the cookie was lost (e.g. Notion
    # redirects through api.notion.com which strips SameSite=Lax cookies), fall back
    # to the DB-stored pending state written during /authorize.
    session_state = request.session.get("oauth_state", "")
    connector_id = request.session.get("oauth_connector", "")

    if session_state and state == session_state:
        # Fast path: cookie survived the redirect
        pass
    else:
        # Slow path: look up state in DB (handles cross-domain OAuth providers)
        db_result = await session.execute(
            select(OAuthPendingState).where(OAuthPendingState.state_token == state)
        )
        pending = db_result.scalar_one_or_none()

        if not pending:
            logger.warning("OAuth state not found in DB: state=%s", state)
            return RedirectResponse(f"{frontend_url}/?settings=Connections&connector_error=state_mismatch")

        if pending.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            logger.warning("OAuth state expired for connector=%s", pending.connector_id)
            await session.delete(pending)
            await session.commit()
            return RedirectResponse(f"{frontend_url}/?settings=Connections&connector_error=state_mismatch")

        connector_id = pending.connector_id
        # Clean up used state token
        await session.delete(pending)
        await session.commit()

    if not connector_id or connector_id not in CONNECTOR_CATALOGUE:
        return RedirectResponse(f"{frontend_url}/?settings=Connections&connector_error=unknown_connector")

    # Get authenticated user
    user = _get_current_user(request)
    uid = user["uid"]

    try:
        connector = get_connector(connector_id)
        # Guard: if credentials aren't configured the exchange will fail with an
        # unhelpful HTTP 401. Surface a clearer error immediately.
        if not connector._client_id or not connector._client_secret:
            logger.error(
                "OAuth exchange aborted for %s: client_id or client_secret not configured. "
                "Set %s_CONNECTOR_CLIENT_ID / %s_CONNECTOR_CLIENT_SECRET env vars or add "
                "credentials via Settings → Connections.",
                connector_id, connector_id.upper(), connector_id.upper(),
            )
            return RedirectResponse(
                f"{frontend_url}/?settings=Connections&connector_error=credentials_not_configured"
            )
        # Notion public integrations send workspace_id / workspace_name as extra
        # callback query params and require them in the token exchange body as
        # external_account. Pass them through when present.
        exchange_kwargs: dict = {}
        if connector_id == "notion":
            ws_id = request.query_params.get("workspace_id", "")
            ws_name = request.query_params.get("workspace_name", "")
            if ws_id:
                exchange_kwargs["workspace_id"] = ws_id
                exchange_kwargs["workspace_name"] = ws_name
        tokens = await connector.exchange_code(code, _callback_uri(), **exchange_kwargs)

        # Get user info from the connected account
        account_info = await connector.get_user_info(tokens.access_token)

        # Encrypt tokens
        access_enc = _key_manager.encrypt(tokens.access_token)
        refresh_enc = _key_manager.encrypt(tokens.refresh_token) if tokens.refresh_token else None

        # Calculate expiry
        expires_at = None
        if tokens.expires_in:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens.expires_in)

        # Upsert connection
        result = await session.execute(
            select(UserConnection).where(
                UserConnection.user_id == uid,
                UserConnection.connector_id == connector_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.access_token_enc = access_enc
            existing.refresh_token_enc = refresh_enc
            existing.token_type = tokens.token_type
            existing.scope = tokens.scope
            existing.expires_at = expires_at
            existing.account_email = account_info.get("email", account_info.get("user", ""))
            existing.account_name = account_info.get("name", account_info.get("team", ""))
            existing.account_avatar = account_info.get("picture", account_info.get("avatar_url", ""))
            existing.raw_metadata = json.dumps(tokens.raw)
            existing.status = "active"
        else:
            connection = UserConnection(
                user_id=uid,
                connector_id=connector_id,
                access_token_enc=access_enc,
                refresh_token_enc=refresh_enc,
                token_type=tokens.token_type,
                scope=tokens.scope,
                expires_at=expires_at,
                account_email=account_info.get("email", account_info.get("user", "")),
                account_name=account_info.get("name", account_info.get("team", "")),
                account_avatar=account_info.get("picture", account_info.get("avatar_url", "")),
                raw_metadata=json.dumps(tokens.raw),
                status="active",
            )
            session.add(connection)

        await session.commit()

        # Clean up session cookie state
        request.session.pop("oauth_state", None)
        request.session.pop("oauth_connector", None)
        # Clean up DB state (may already be deleted in slow-path above, ignore if missing)
        try:
            db_pending = await session.execute(
                select(OAuthPendingState).where(OAuthPendingState.state_token == state)
            )
            leftover = db_pending.scalar_one_or_none()
            if leftover:
                await session.delete(leftover)
                await session.commit()
        except Exception:
            pass

        logger.info("Connected %s for user %s", connector_id, uid)
        return RedirectResponse(f"{frontend_url}/?settings=Connections&connector_connected={connector_id}")

    except Exception as exc:
        # Log the real HTTP body if it's an httpx error so Railway logs show why
        detail = str(exc)
        if hasattr(exc, "response") and exc.response is not None:  # type: ignore[union-attr]
            try:
                detail = f"HTTP {exc.response.status_code}: {exc.response.text[:400]}"  # type: ignore[union-attr]
            except Exception:
                pass
        logger.error("OAuth exchange failed for %s: %s", connector_id, detail, exc_info=True)
        from urllib.parse import quote
        safe_detail = quote(detail[:120], safe="")
        return RedirectResponse(
            f"{frontend_url}/?settings=Connections&connector_error=exchange_failed&connector_error_detail={safe_detail}"
        )


# ── Disconnect ────────────────────────────────────────────────────────


@connector_router.post("/{connector_id}/disconnect")
async def disconnect_connector(
    connector_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Revoke tokens and delete the connection."""
    user = _get_current_user(request)
    uid = user["uid"]

    result = await session.execute(
        select(UserConnection).where(
            UserConnection.user_id == uid,
            UserConnection.connector_id == connector_id,
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Try to revoke the token
    try:
        connector = get_connector(connector_id)
        access_token = _key_manager.decrypt(connection.access_token_enc)
        await connector.revoke(access_token)
    except Exception as exc:
        logger.warning("Token revocation failed for %s (proceeding with deletion): %s", connector_id, exc)

    await session.delete(connection)
    await session.commit()

    logger.info("Disconnected %s for user %s", connector_id, uid)
    return {"ok": True, "connector_id": connector_id}


# ── Execute action ────────────────────────────────────────────────────


@connector_router.post("/{connector_id}/execute")
async def execute_connector_action(
    connector_id: str,
    request: Request,
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Execute an action on a connected service.

    Body: { "action": "gmail_list_messages", "params": { ... } }
    """
    user = _get_current_user(request)
    uid = user["uid"]

    # Get connection
    result = await session.execute(
        select(UserConnection).where(
            UserConnection.user_id == uid,
            UserConnection.connector_id == connector_id,
        )
    )
    connection = result.scalar_one_or_none()

    if not connection or connection.status != "active":
        raise HTTPException(status_code=400, detail=f"No active {connector_id} connection. Please connect first.")

    action_id = payload.get("action", "")
    params = payload.get("params", {})

    if not action_id:
        raise HTTPException(status_code=400, detail="action is required")

    capability_status, _ = resolve_capability_status(connector_id, action_id)
    if capability_status != "supported":
        return unsupported_action_fallback(connector_id, action_id)

    # Decrypt access token
    try:
        access_token = _key_manager.decrypt(connection.access_token_enc)
    except ValueError:
        connection.status = "expired"
        await session.commit()
        raise HTTPException(status_code=401, detail="Connection expired. Please reconnect.")

    connector = get_connector(connector_id)

    # Check if token is expired and try refresh
    if connection.expires_at and connection.expires_at < datetime.now(timezone.utc):
        if connection.refresh_token_enc:
            try:
                refresh_token = _key_manager.decrypt(connection.refresh_token_enc)
                new_tokens = await connector.refresh_tokens(refresh_token)
                connection.access_token_enc = _key_manager.encrypt(new_tokens.access_token)
                if new_tokens.refresh_token:
                    connection.refresh_token_enc = _key_manager.encrypt(new_tokens.refresh_token)
                if new_tokens.expires_in:
                    connection.expires_at = datetime.now(timezone.utc) + timedelta(seconds=new_tokens.expires_in)
                connection.status = "active"
                await session.commit()
                access_token = new_tokens.access_token
                logger.info("Refreshed token for %s user %s", connector_id, uid)
            except Exception as exc:
                logger.warning("Token refresh failed for %s: %s", connector_id, exc)
                connection.status = "expired"
                await session.commit()
                raise HTTPException(status_code=401, detail="Token expired and refresh failed. Please reconnect.")
        else:
            connection.status = "expired"
            await session.commit()
            raise HTTPException(status_code=401, detail="Token expired. Please reconnect.")

    try:
        result_data = await connector.execute_action(action_id, params, access_token)
        return {"ok": True, "result": result_data}
    except Exception as exc:
        logger.exception("Connector action failed: %s/%s", connector_id, action_id)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Save OAuth app credentials ────────────────────────────────────────


@connector_router.post("/{connector_id}/credentials")
async def save_connector_credentials(
    connector_id: str,
    payload: dict[str, Any],
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Save OAuth app credentials (client_id / client_secret) to the DB.

    Allows admins to configure connectors through the UI without setting
    Railway environment variables.
    """
    current_user = _get_current_user(request)  # must be authenticated
    if current_user.get("role") not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Only admins can configure OAuth app credentials")

    client_id = payload.get("client_id", "").strip()
    client_secret = payload.get("client_secret", "").strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="client_id and client_secret are required")

    from backend.database import OAuthAppCredential

    existing = await session.execute(
        select(OAuthAppCredential).where(OAuthAppCredential.connector_id == connector_id)
    )
    cred = existing.scalar_one_or_none()
    if cred:
        cred.client_id_enc = _key_manager.encrypt(client_id)
        cred.client_secret_enc = _key_manager.encrypt(client_secret)
    else:
        cred = OAuthAppCredential(
            connector_id=connector_id,
            client_id_enc=_key_manager.encrypt(client_id),
            client_secret_enc=_key_manager.encrypt(client_secret),
        )
        session.add(cred)

    await session.commit()
    logger.info("Saved OAuth app credentials for connector %s", connector_id)
    return {"ok": True}


# ── List actions ──────────────────────────────────────────────────────


@connector_router.get("/{connector_id}/actions")
async def list_connector_actions(
    connector_id: str,
    request: Request,
) -> dict[str, Any]:
    """List all actions available for a connector."""
    _get_current_user(request)

    if connector_id not in CONNECTOR_CATALOGUE:
        raise HTTPException(status_code=404, detail=f"Unknown connector: {connector_id}")

    connector = get_connector(connector_id)
    actions = connector.list_actions()

    return {
        "ok": True,
        "connector_id": connector_id,
        "actions": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "parameters": a.parameters,
                "category": a.category,
            }
            for a in actions
        ],
    }
