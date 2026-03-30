"""Authentication routes and helpers for OAuth + email sign-in.

Uses PostgreSQL/SQLAlchemy instead of Firestore for user and auth-code storage.
"""

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

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from httpx import HTTPError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AuthCode, User, get_session
from backend.email_service import send_magic_link_email, send_welcome_email
from config import settings

logger = logging.getLogger(__name__)

try:
    import aiosmtplib
except ModuleNotFoundError:  # pragma: no cover - optional local dependency
    aiosmtplib = None

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth = OAuth()


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


def _require_session_secret() -> None:
    if not settings.SESSION_SECRET:
        raise HTTPException(status_code=500, detail="SESSION_SECRET is not configured")


def _sign_session(payload: dict[str, Any]) -> str:
    _require_session_secret()
    session_payload = dict(payload)
    session_payload["exp"] = int(time.time()) + int(settings.SESSION_TTL_SECONDS)
    raw = json.dumps(session_payload, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")
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
        response = JSONResponse(jsonable_encoder({"ok": True, "user": user}))
    response.set_cookie(
        "aegis_session",
        token,
        max_age=int(settings.SESSION_TTL_SECONDS),
        httponly=True,
        secure=bool(settings.COOKIE_SECURE),
        samesite=settings.normalized_cookie_samesite,
        domain=settings.resolved_cookie_domain,
        path="/",
    )
    return response


def _normalized_admin_emails() -> set[str]:
    """Return the configured admin email allowlist normalized for lookup."""
    return {email.strip().lower() for email in settings.ADMIN_EMAILS.split(",") if email.strip()}


async def _upsert_user(session: AsyncSession, profile: dict[str, Any]) -> dict[str, Any]:
    """Create or update a user record in PostgreSQL."""
    now = datetime.now(timezone.utc)
    existing = await session.get(User, profile["uid"])
    if existing:
        existing.provider = profile.get("provider")
        existing.provider_id = profile.get("provider_id")
        existing.email = profile.get("email")
        existing.name = profile.get("name")
        existing.avatar_url = profile.get("avatar_url")
        if profile.get("password_hash"):
            existing.password_hash = profile["password_hash"]
        if existing.status and existing.status != "active":
            raise HTTPException(status_code=403, detail="Account suspended")
        existing.last_login_at = now
        payload = {
            "uid": existing.uid,
            "provider": existing.provider,
            "provider_id": existing.provider_id,
            "email": existing.email,
            "name": existing.name,
            "avatar_url": existing.avatar_url,
            "role": existing.role or "user",
            "status": existing.status or "active",
            "created_at": existing.created_at,
            "last_login_at": now,
        }
    else:
        profile_email = str(profile.get("email", "")).strip().lower()
        role = "admin" if profile_email and profile_email in _normalized_admin_emails() else "user"
        user = User(
            uid=profile["uid"],
            provider=profile.get("provider"),
            provider_id=profile.get("provider_id"),
            email=profile.get("email"),
            name=profile.get("name"),
            avatar_url=profile.get("avatar_url"),
            role=role,
            status="active",
            password_hash=profile.get("password_hash"),
            created_at=now,
            last_login_at=now,
        )
        session.add(user)
        payload = {
            "uid": user.uid,
            "provider": user.provider,
            "provider_id": user.provider_id,
            "email": user.email,
            "name": user.name,
            "avatar_url": user.avatar_url,
            "role": user.role,
            "status": user.status,
            "created_at": now,
            "last_login_at": now,
        }
        await session.commit()
        # Fire-and-forget welcome email for new users
        if user.email:
            try:
                await send_welcome_email(user.email, user.name or "")
            except Exception:  # noqa: BLE001
                logger.exception("Failed to send welcome email to %s", user.email)
        return payload
    await session.commit()
    return payload


def _callback_url(provider: str) -> str:
    base = settings.resolved_public_base_url
    return f"{base}/api/auth/{provider}/callback"


def _frontend_redirect() -> str:
    return settings.resolved_frontend_url or "/"


async def _send_email(recipient: str, subject: str, body: str) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_SENDER:
        raise HTTPException(status_code=500, detail="SMTP is not configured")
    if aiosmtplib is None:
        raise HTTPException(status_code=500, detail="Email sign-in is unavailable: aiosmtplib is not installed")
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


def _password_uid(email: str) -> str:
    return f"password:{email}"


def _hash_password(password: str) -> str:
    _require_session_secret()
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt + settings.SESSION_SECRET.encode("utf-8"),
        120_000,
    )
    return f"pbkdf2_sha256${salt.hex()}${derived.hex()}"


def _verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, salt_hex, digest_hex = password_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex) + settings.SESSION_SECRET.encode("utf-8"),
        120_000,
    )
    return hmac.compare_digest(derived.hex(), digest_hex)


# ── OAuth routes ──────────────────────────────────────────────────────


@router.get("/google/login")
async def google_login(request: Request) -> RedirectResponse:
    """Start Google OAuth flow."""
    if not hasattr(oauth, "google"):
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    return await oauth.google.authorize_redirect(request, _callback_url("google"))


@router.get("/google/callback")
async def google_callback(request: Request, session: AsyncSession = Depends(get_session)) -> RedirectResponse:
    """Handle Google OAuth callback."""
    try:
        token = await oauth.google.authorize_access_token(request, redirect_uri=_callback_url("google"))
    except OAuthError as exc:
        logger.warning("Google OAuth token exchange error: %s", exc.error)
        raise HTTPException(status_code=400, detail="Google OAuth failed") from exc

    info: dict[str, Any]
    try:
        info = await oauth.google.parse_id_token(request, token)
    except OAuthError as exc:
        logger.warning("Google OAuth ID token parse error: %s", exc.error)
        try:
            userinfo_resp = await oauth.google.get("userinfo", token=token)
            userinfo_resp.raise_for_status()
            info = userinfo_resp.json()
        except (OAuthError, HTTPError, json.JSONDecodeError) as fallback_exc:
            logger.warning("Google OAuth userinfo fallback also failed: %s", fallback_exc)
            raise HTTPException(status_code=400, detail="Google OAuth failed") from fallback_exc

    provider_id = info.get("sub")
    if not provider_id:
        logger.warning("Google OAuth userinfo missing sub claim")
        raise HTTPException(status_code=400, detail="Google OAuth failed")

    profile = {
        "uid": f"google:{provider_id}",
        "provider": "google",
        "provider_id": provider_id,
        "email": info.get("email"),
        "name": info.get("name") or info.get("email"),
        "avatar_url": info.get("picture"),
    }
    user = await _upsert_user(session, profile)
    return _session_response(user, redirect=_frontend_redirect())


@router.get("/github/login")
async def github_login(request: Request) -> RedirectResponse:
    """Start GitHub OAuth flow."""
    if not hasattr(oauth, "github"):
        raise HTTPException(status_code=400, detail="GitHub OAuth is not configured")
    return await oauth.github.authorize_redirect(request, _callback_url("github"))


@router.get("/github/callback")
async def github_callback(request: Request, session: AsyncSession = Depends(get_session)) -> RedirectResponse:
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
    user = await _upsert_user(session, profile)
    return _session_response(user, redirect=_frontend_redirect())


@router.get("/sso/login")
async def sso_login(request: Request) -> RedirectResponse:
    """Start generic SSO (OIDC) flow."""
    if not hasattr(oauth, "sso"):
        raise HTTPException(status_code=400, detail="SSO OAuth is not configured")
    return await oauth.sso.authorize_redirect(request, _callback_url("sso"))


@router.get("/sso/callback")
async def sso_callback(request: Request, session: AsyncSession = Depends(get_session)) -> RedirectResponse:
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
    user = await _upsert_user(session, profile)
    return _session_response(user, redirect=_frontend_redirect())


# ── Email sign-in ─────────────────────────────────────────────────────


@router.post("/email/start")
async def email_start(payload: dict[str, Any], session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Send a one-time sign-in code to the provided email address."""
    email = str(payload.get("email", "")).strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = _hash_code(code)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    try:
        existing = await session.get(AuthCode, email)
        if existing:
            existing.code_hash = code_hash
            existing.expires_at = expires_at
        else:
            session.add(AuthCode(email=email, code_hash=code_hash, expires_at=expires_at))
        await session.commit()
        await send_magic_link_email(email, code)
    except Exception as exc:
        logger.exception("Email sign-in failed for %s", email)
        raise HTTPException(status_code=500, detail=f"Email sign-in failed: {exc}") from exc

    return {"ok": True}


@router.post("/email/check")
async def email_check(payload: dict[str, Any], session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Check whether a password-based account already exists for the given email."""
    email = str(payload.get("email", "")).strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    existing = await session.get(User, _password_uid(email))
    return {"exists": existing is not None}


@router.post("/password/signup")
async def password_signup(payload: dict[str, Any], session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """Create a password-based account and sign the user in."""
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", "")).strip()
    name = str(payload.get("name", "")).strip() or email.split("@", 1)[0]
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    existing = await session.get(User, _password_uid(email))
    if existing:
        raise HTTPException(status_code=409, detail="Account already exists. Sign in instead.")

    profile = {
        "uid": _password_uid(email),
        "provider": "password",
        "provider_id": email,
        "email": email,
        "name": name,
        "avatar_url": None,
        "password_hash": _hash_password(password),
    }
    user = await _upsert_user(session, profile)
    return _session_response(user)


@router.post("/password/login")
async def password_login(payload: dict[str, Any], session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """Sign in with an existing password-based account."""
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", "")).strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")

    existing = await session.get(User, _password_uid(email))
    if existing and existing.status and existing.status != "active":
        raise HTTPException(status_code=403, detail="Account suspended")
    if not existing or not _verify_password(password, existing.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    existing.last_login_at = datetime.now(timezone.utc)
    await session.commit()
    user = {
        "uid": existing.uid,
        "provider": existing.provider,
        "provider_id": existing.provider_id,
        "email": existing.email,
        "name": existing.name,
        "avatar_url": existing.avatar_url,
        "role": existing.role or "user",
        "status": existing.status or "active",
        "created_at": existing.created_at,
        "last_login_at": existing.last_login_at,
    }
    return _session_response(user)


@router.post("/email/verify")
async def email_verify(payload: dict[str, Any], session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """Verify a one-time code and issue a session."""
    email = str(payload.get("email", "")).strip().lower()
    code = str(payload.get("code", "")).strip()
    if not email or not code:
        raise HTTPException(status_code=400, detail="Email and code are required")

    record = await session.get(AuthCode, email)
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    if record.expires_at and record.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Code expired")

    if record.code_hash != _hash_code(code):
        raise HTTPException(status_code=400, detail="Invalid code")

    await session.execute(delete(AuthCode).where(AuthCode.email == email))
    await session.commit()

    profile = {
        "uid": f"email:{email}",
        "provider": "email",
        "provider_id": email,
        "email": email,
        "name": email.split("@", 1)[0],
        "avatar_url": None,
    }
    user = await _upsert_user(session, profile)
    return _session_response(user)


# ── Session routes ────────────────────────────────────────────────────


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
