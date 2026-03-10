"""Simple encrypted local credential store for integrations."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet

from config import settings


class SecureStore:
    """In-memory encrypted store keyed by user/integration identifiers."""

    def __init__(self) -> None:
        self._fernet = Fernet(self._derive_key(settings.INTEGRATIONS_ENCRYPTION_KEY))
        self._values: dict[str, bytes] = {}

    def _derive_key(self, value: str) -> bytes:
        seed = value.strip() or "local-dev-insecure-key-change-me"
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    def set_secret(self, key: str, payload: dict[str, Any]) -> str:
        """Encrypt and store payload under key; return storage key."""
        token = self._fernet.encrypt(json.dumps(payload).encode("utf-8"))
        self._values[key] = token
        return key

    def get_secret(self, key: str | None) -> dict[str, str]:
        """Read and decrypt payload for key."""
        if not key:
            return {}
        encrypted = self._values.get(key)
        if encrypted is None:
            return {}
        raw = self._fernet.decrypt(encrypted).decode("utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return {}
        return {str(k): str(v) for k, v in parsed.items()}

    def mask(self, secret: str) -> str:
        """Return masked secret representation safe for UI."""
        if not secret:
            return ""
        if len(secret) < 6:
            return "••••"
        return f"••••{secret[-4:]}"
