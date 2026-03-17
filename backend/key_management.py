"""BYOK (Bring Your Own Key) management module.

Encrypts API keys at rest using Fernet symmetric encryption.
The encryption key is derived from ``ENCRYPTION_SECRET`` in the environment.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import UserAPIKey
from backend.providers import PROVIDER_CATALOGUE

logger = logging.getLogger(__name__)


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a 32-byte Fernet key from an arbitrary secret string."""
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


class KeyManager:
    """Manages encrypted storage of user-supplied API keys."""

    def __init__(self, encryption_secret: str) -> None:
        self._fernet = Fernet(_derive_fernet_key(encryption_secret))

    def encrypt(self, plaintext: str) -> str:
        """Encrypt an API key string."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a stored API key."""
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            raise ValueError("Failed to decrypt API key — encryption secret may have changed")

    @staticmethod
    def mask_key(key: str) -> str:
        """Return a masked version safe for display (e.g. ``sk-...abc``)."""
        if len(key) <= 8:
            return "••••••"
        return f"{key[:4]}••••{key[-4:]}"

    async def store_key(
        self,
        session: AsyncSession,
        uid: str,
        provider: str,
        api_key: str,
    ) -> dict[str, str]:
        """Encrypt and store (or update) a user's API key for a provider."""
        if provider not in PROVIDER_CATALOGUE:
            raise ValueError(f"Unsupported provider: {provider}")

        encrypted = self.encrypt(api_key)
        hint = self.mask_key(api_key)

        existing = await session.get(UserAPIKey, (uid, provider))
        if existing:
            existing.encrypted_key = encrypted
            existing.key_hint = hint
        else:
            session.add(UserAPIKey(
                uid=uid,
                provider=provider,
                encrypted_key=encrypted,
                key_hint=hint,
            ))
        await session.commit()
        logger.info("Stored API key for user=%s provider=%s", uid, provider)
        return {"provider": provider, "key_hint": hint}

    async def get_key(
        self,
        session: AsyncSession,
        uid: str,
        provider: str,
    ) -> str | None:
        """Retrieve and decrypt a stored API key."""
        record = await session.get(UserAPIKey, (uid, provider))
        if not record:
            return None
        return self.decrypt(record.encrypted_key)

    async def delete_key(
        self,
        session: AsyncSession,
        uid: str,
        provider: str,
    ) -> bool:
        """Delete a stored API key."""
        result = await session.execute(
            delete(UserAPIKey).where(
                UserAPIKey.uid == uid,
                UserAPIKey.provider == provider,
            )
        )
        await session.commit()
        deleted = result.rowcount > 0  # type: ignore[union-attr]
        if deleted:
            logger.info("Deleted API key for user=%s provider=%s", uid, provider)
        return deleted

    async def list_keys(
        self,
        session: AsyncSession,
        uid: str,
    ) -> list[dict[str, str]]:
        """List all stored provider keys for a user (hints only, no secrets)."""
        result = await session.execute(
            select(UserAPIKey).where(UserAPIKey.uid == uid)
        )
        rows = result.scalars().all()
        return [
            {
                "provider": row.provider,
                "key_hint": row.key_hint or "",
                "has_key": True,
            }
            for row in rows
        ]
