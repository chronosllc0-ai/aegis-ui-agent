"""Authentication routes and helpers for OAuth + email sign-in."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

import aiosmtplib
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from google.cloud import firestore

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth = OAuth()
_firestore_client: firestore.AsyncClient | None = None


def _register_oauth_providers() -> None:
    if settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET:
        oauth.register(
            name="google",
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    if settings.GITHUB_OAUTH_CLIENT_ID and settings.GITHUB_OAUTH_CLIENT_SECRET:
        oauth.register(
            name="github",
            client_id=settings.GITHUB_OAUTH_CLIENT_ID,
            client_secret=settings.GITHUB_OAUTH_CLIENT_SECRET,
            authorize_url="https://github.com/login/oauth/authorize",
            access_token_url="https://github.com/login/oauth/access_token",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user user:email"},
        )
    if settings.SSO_OIDC_METADATA_URL and settings.SSO_CLIENT_ID and settings.SSO_CLIENT_SECRET:
        oauth.register(
            name="sso",
            client_id=settings.SSO_CLIENT_ID,
            client_secret=settings.SSO_CLIENT_SECRET,
            server_metadata_url=settings.SSO_OIDC_METADATA_URL,
            client_kwargs={"scope": settings.SSO_SCOPE},
        )


_register_oauth_providers()


def _get_firestore_client() -> firestore.AsyncClient:
    global _firestore_client
    if _firestore_client is None:
        project = settings.GOOGLE_CLOUD_PROJECT or None
        _firestore_client = firestore.AsyncClient(project=project)
    return _firestore_client


def _require_session_secret() -> None:
    if not settings.SESSION_SECRET:
        raise HTTPException(status_code=500, detail="SESSION_SECRET is not configured")


def _sign_session(payload: dict[str, Any]) -> str:
    _require_session_secret()
    session_payload = dict(payload)
    session_payload["exp"] = int(time.time()) + int(settings.SESSION_TTL_SECONDS)
    raw = json.dumps(session_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
    signature = hmac.new(settings.SESSION_SECRET.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _verify_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    _require_session_secret()
    try:
        encoded, signature = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(settings.SESSION_SECRET.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")))
    except (ValueError, json.JSONDecodeError):
        return None
    exp = int(payload.get("exp", 0))
    if exp and exp < int(time.time()):
        return None
    return payload


def _session_response(user: dict[str, Any], redirect: str | None = None) -> RedirectResponse | JSONResponse:
    token = _sign_session(user)
    if redirect:
        response = RedirectResponse(redirect)
    else:
        response = JSONResponse({"ok": True, "user": user})
    response.set_cookie(
        "aegis_session",
        token,
        max_age=int(settings.SESSION_TTL_SECONDS),
        httponly=True,
        secure=bool(settings.COOKIE_SECURE),
        samesite="lax",
        path="/",
    )
    return response


async def _upsert_user(profile: dict[str, Any]) -> dict[str, Any]:
    client = _get_firestore_client()
    now = datetime.now(timezone.utc)
    doc_ref = client.collection("users").document(profile["uid"])
    snapshot = await doc_ref.get()
    payload = {
        "uid": profile["uid"],
        "provider": profile.get("provider"),
        "provider_id": profile.get("provider_id"),
        "email": profile.get("email"),
        "name": profile.get("name"),
        "avatar_url": profile.get("avatar_url"),
        "last_login_at": now,
    }
    if snapshot.exists:
        existing = snapshot.to_dict() or {}
        payload["created_at"] = existing.get("created_at", now)
    else:
        payload["created_at"] = now
    await doc_ref.set(payload, merge=True)
    return payload


def _callback_url(provider: str) -> str:
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/api/auth/{provider}/callback"


def _frontend_redirect() -> str:
    return settings.FRONTEND_URL or "/"


async def _send_email(recipient: str, subject: str, body: str) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_SENDER:
        raise HTTPException(status_code=500, detail="SMTP is not configured")
    message = EmailMessage()
    message["From"] = settings.SMTP_SENDER
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=int(settings.SMTP_PORT),
        username=settings.SMTP_USERNAME or None,
        password=settings.SMTP_PASSWORD or None,
        start_tls=bool(settings.SMTP_USE_TLS),
    )


def _hash_code(code: str) -> str:
    _require_session_secret()
    return hmac.new(settings.SESSION_SECRET.encode("utf-8"), code.encode("utf-8"), hashlib.sha256).hexdigest()


@router.get("/google/login")
async def google_login(request: Request) -> RedirectResponse:
    """Start Google OAuth flow."""
    if not hasattr(oauth, "google"):
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    return await oauth.google.authorize_redirect(request, _callback_url("google"))


@router.get("/google/callback")
async def google_callback(request: Request) -> RedirectResponse:
    """Handle Google OAuth callback."""
    try:
        token = await oauth.google.authorize_access_token(request)
        info = await oauth.google.parse_id_token(request, token)
    except OAuthError as exc:
        logger.warning("Google OAuth error: %s", exc.error)
        raise HTTPException(status_code=400, detail="Google OAuth failed") from exc

    profile = {
        "uid": f"google:{info.get('sub')}",
        "provider": "google",
        "provider_id": info.get("sub"),
        "email": info.get("email"),
        "name": info.get("name") or info.get("email"),
        "avatar_url": info.get("picture"),
    }
    user = await _upsert_user(profile)
    return _session_response(user, redirect=_frontend_redirect())


@router.get("/github/login")
async def github_login(request: Request) -> RedirectResponse:
    """Start GitHub OAuth flow."""
    if not hasattr(oauth, "github"):
        raise HTTPException(status_code=400, detail="GitHub OAuth is not configured")
    return await oauth.github.authorize_redirect(request, _callback_url("github"))


@router.get("/github/callback")
async def github_callback(request: Request) -> RedirectResponse:
    """Handle GitHub OAuth callback."""
    try:
        token = await oauth.github.authorize_access_token(request)
    except OAuthError as exc:
        logger.warning("GitHub OAuth error: %s", exc.error)
        raise HTTPException(status_code=400, detail="GitHub OAuth failed") from exc

    user_resp = await oauth.github.get("user", token=token)
    profile_data = user_resp.json()
    email = profile_data.get("email")
    if not email:
        emails_resp = await oauth.github.get("user/emails", token=token)
        emails = emails_resp.json()
        primary = next((entry for entry in emails if entry.get("primary") and entry.get("verified")), None)
        if primary:
            email = primary.get("email")

    profile = {
        "uid": f"github:{profile_data.get('id')}",
        "provider": "github",
        "provider_id": profile_data.get("id"),
        "email": email,
        "name": profile_data.get("name") or profile_data.get("login"),
        "avatar_url": profile_data.get("avatar_url"),
    }
    user = await _upsert_user(profile)
    return _session_response(user, redirect=_frontend_redirect())


@router.get("/sso/login")
async def sso_login(request: Request) -> RedirectResponse:
    """Start generic SSO (OIDC) flow."""
    if not hasattr(oauth, "sso"):
        raise HTTPException(status_code=400, detail="SSO OAuth is not configured")
    return await oauth.sso.authorize_redirect(request, _callback_url("sso"))


@router.get("/sso/callback")
async def sso_callback(request: Request) -> RedirectResponse:
    """Handle generic SSO (OIDC) callback."""
    try:
        token = await oauth.sso.authorize_access_token(request)
        info = await oauth.sso.parse_id_token(request, token)
    except OAuthError as exc:
        logger.warning("SSO OAuth error: %s", exc.error)
        raise HTTPException(status_code=400, detail="SSO OAuth failed") from exc

    profile = {
        "uid": f"sso:{info.get('sub')}",
        "provider": "sso",
        "provider_id": info.get("sub"),
        "email": info.get("email"),
        "name": info.get("name") or info.get("email"),
        "avatar_url": info.get("picture"),
    }
    user = await _upsert_user(profile)
    return _session_response(user, redirect=_frontend_redirect())


@router.post("/email/start")
async def email_start(payload: dict[str, Any]) -> dict[str, Any]:
    """Send a one-time sign-in code to the provided email address."""
    email = str(payload.get("email", "")).strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = _hash_code(code)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    try:
        client = _get_firestore_client()
        await client.collection("auth_codes").document(email).set(
            {
                "code_hash": code_hash,
                "expires_at": expires_at,
                "created_at": datetime.now(timezone.utc),
            }
        )
        await _send_email(email, "Your Aegis sign-in code", f"Your code is {code}. It expires in 10 minutes.")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Email sign-in failed for %s", email)
        raise HTTPException(status_code=500, detail=f"Email sign-in failed: {exc}") from exc

    return {"ok": True}


@router.post("/email/verify")
async def email_verify(payload: dict[str, Any]) -> JSONResponse:
    """Verify a one-time code and issue a session."""
    email = str(payload.get("email", "")).strip().lower()
    code = str(payload.get("code", "")).strip()
    if not email or not code:
        raise HTTPException(status_code=400, detail="Email and code are required")

    client = _get_firestore_client()
    doc_ref = client.collection("auth_codes").document(email)
    snapshot = await doc_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    data = snapshot.to_dict() or {}
    expires_at = data.get("expires_at")
    if isinstance(expires_at, datetime) and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Code expired")

    if data.get("code_hash") != _hash_code(code):
        raise HTTPException(status_code=400, detail="Invalid code")

    await doc_ref.delete()

    profile = {
        "uid": f"email:{email}",
        "provider": "email",
        "provider_id": email,
        "email": email,
        "name": email.split("@", 1)[0],
        "avatar_url": None,
    }
    user = await _upsert_user(profile)
    return _session_response(user)


@router.get("/me")
async def me(request: Request) -> dict[str, Any]:
    """Return the current authenticated user."""
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"ok": True, "user": payload}


@router.post("/logout")
async def logout() -> JSONResponse:
    """Clear the auth session cookie."""
    response = JSONResponse({"ok": True})
    response.delete_cookie("aegis_session", path="/")
    return response
