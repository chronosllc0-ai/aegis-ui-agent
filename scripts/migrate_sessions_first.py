"""Archive legacy task/thread data and enforce sessions-first defaults.

Usage:
    python scripts/migrate_sessions_first.py
"""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from backend.database import User, get_session, init_db
from backend.sessions_migration_service import migrate_user_to_sessions_first
from config import settings


async def run() -> None:
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required to run sessions-first migration")
    init_db(settings.DATABASE_URL)

    results: list[dict[str, int | str]] = []
    async for db in get_session():
        user_ids = (await db.execute(select(User.uid))).scalars().all()
        for uid in user_ids:
            results.append(await migrate_user_to_sessions_first(db, user_id=uid, platform="web"))
        break

    print(json.dumps({"ok": True, "migrated_users": len(results), "results": results}, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
