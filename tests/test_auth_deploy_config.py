"""Deployment configuration regression tests for auth/session behavior."""

from __future__ import annotations

import auth
from config import settings


def test_resolved_public_base_url_prefers_explicit_value(monkeypatch) -> None:
    """Explicit PUBLIC_BASE_URL should win over Railway-derived values."""
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://api.mohex.org/")
    monkeypatch.setattr(settings, "RAILWAY_PUBLIC_DOMAIN", "aegis-production.up.railway.app")
    monkeypatch.setattr(settings, "PORT", 8000)

    assert settings.resolved_public_base_url == "https://api.mohex.org"


def test_resolved_public_base_url_falls_back_to_railway_domain(monkeypatch) -> None:
    """Railway public domain should produce a valid https base URL when PUBLIC_BASE_URL is unset."""
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "")
    monkeypatch.setattr(settings, "RAILWAY_PUBLIC_DOMAIN", "aegis-production.up.railway.app")

    assert settings.resolved_public_base_url == "https://aegis-production.up.railway.app"
    assert auth._callback_url("github") == "https://aegis-production.up.railway.app/api/auth/github/callback"


def test_session_response_uses_configured_cookie_policy(monkeypatch) -> None:
    """Cookie settings should be configurable for split frontend/backend deploys."""
    monkeypatch.setattr(settings, "SESSION_SECRET", "test-session-secret")
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "none")
    monkeypatch.setattr(settings, "COOKIE_DOMAIN", "aegis-production.up.railway.app")

    response = auth._session_response({"uid": "user-1", "email": "user@example.com"})
    cookie_header = response.headers["set-cookie"]

    assert "Secure" in cookie_header
    assert "SameSite=none" in cookie_header
    assert "Domain=aegis-production.up.railway.app" in cookie_header
