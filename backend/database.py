"""PostgreSQL database setup with SQLAlchemy async engine.

Falls back to SQLite when ``DATABASE_URL`` is unset (local development).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import Column, DateTime, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Shared declarative base for all models."""


class User(Base):
    """Registered user account."""

    __tablename__ = "users"

    uid = Column(String(255), primary_key=True)
    provider = Column(String(50))
    provider_id = Column(String(255))
    email = Column(String(320))
    name = Column(String(255))
    avatar_url = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), onupdate=func.now())


class AuthCode(Base):
    """Temporary email verification code."""

    __tablename__ = "auth_codes"

    email = Column(String(320), primary_key=True)
    code_hash = Column(String(128), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserAPIKey(Base):
    """Encrypted API key for a specific provider (BYOK)."""

    __tablename__ = "user_api_keys"

    uid = Column(String(255), primary_key=True)
    provider = Column(String(50), primary_key=True)
    encrypted_key = Column(Text, nullable=False)
    key_hint = Column(String(20), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ── engine management ─────────────────────────────────────────────────

_engine = None
_session_factory = None


def _resolve_url(url: str) -> str:
    """Translate standard ``postgres://`` or ``postgresql://`` to async drivers."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def init_db(database_url: str | None = None) -> None:
    """Create the async engine and session factory.

    Call once at application startup.  If *database_url* is ``None`` the
    engine uses an in-memory SQLite database (for local dev / tests).
    """
    global _engine, _session_factory

    if database_url:
        url = _resolve_url(database_url)
    else:
        url = "sqlite+aiosqlite:///./aegis_dev.db"
        logger.warning("DATABASE_URL not set — using local SQLite at ./aegis_dev.db")

    _engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def create_tables() -> None:
    """Create all tables if they don't exist."""
    if _engine is None:
        raise RuntimeError("Call init_db() before create_tables()")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session (for FastAPI dependency injection)."""
    if _session_factory is None:
        raise RuntimeError("Call init_db() before using get_session()")
    async with _session_factory() as session:
        yield session
