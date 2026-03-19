"""Seed or update a password-based superadmin account."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auth import _hash_password, _password_uid
from backend import database
from backend.database import User
from config import settings


async def seed_super_admin(
    *,
    email: str,
    password: str,
    name: str,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Create or update a password-based superadmin user."""
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("email is required")
    if not password:
        raise ValueError("password is required")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")

    database.init_db(database_url or settings.DATABASE_URL or None)
    await database.create_tables()

    uid = _password_uid(normalized_email)
    created = False
    now = datetime.now(timezone.utc)

    async with database._session_factory() as session:  # type: ignore[union-attr]
        user = await session.get(User, uid)
        if user is None:
            created = True
            user = User(
                uid=uid,
                provider="password",
                provider_id=normalized_email,
                email=normalized_email,
                name=name.strip() or normalized_email.split("@", 1)[0],
                avatar_url=None,
                role="superadmin",
                status="active",
                password_hash=_hash_password(password),
                created_at=now,
                last_login_at=now,
            )
            session.add(user)
        else:
            user.provider = "password"
            user.provider_id = normalized_email
            user.email = normalized_email
            user.name = name.strip() or normalized_email.split("@", 1)[0]
            user.role = "superadmin"
            user.status = "active"
            user.password_hash = _hash_password(password)
            user.last_login_at = now

        await session.commit()

    return {
        "ok": True,
        "created": created,
        "uid": uid,
        "email": normalized_email,
        "role": "superadmin",
    }


def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser for the seed script."""
    parser = argparse.ArgumentParser(description="Seed or update the Aegis superadmin account.")
    parser.add_argument("--email", required=True, help="Superadmin email address")
    parser.add_argument("--password", required=True, help="Superadmin password")
    parser.add_argument("--name", default="Super Admin", help="Display name")
    parser.add_argument("--database-url", default=None, help="Optional database URL override")
    return parser


def main() -> None:
    """Run the CLI entrypoint."""
    args = _build_parser().parse_args()
    result = asyncio.run(
        seed_super_admin(
            email=args.email,
            password=args.password,
            name=args.name,
            database_url=args.database_url,
        )
    )
    print(
        f"Seeded superadmin {result['email']} "
        f"({ 'created' if result['created'] else 'updated' })"
    )


if __name__ == "__main__":
    main()
