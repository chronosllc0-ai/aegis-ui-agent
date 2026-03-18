"""PostgreSQL database setup with SQLAlchemy async engine.

Falls back to SQLite when ``DATABASE_URL`` is unset (local development).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func, inspect, text
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
    password_hash = Column(Text)
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


class CreditBalance(Base):
    """Per-user credit balance for the current billing cycle."""

    __tablename__ = "credit_balances"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), unique=True, nullable=False, index=True)
    plan = Column(String(50), default="free")
    monthly_allowance = Column(Integer, default=1000)
    credits_used = Column(Integer, default=0)
    overage_credits = Column(Integer, default=0)
    cycle_start = Column(DateTime(timezone=True), nullable=False)
    cycle_end = Column(DateTime(timezone=True), nullable=False)
    spending_cap = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UsageEvent(Base):
    """Individual AI usage event — one per provider API call."""

    __tablename__ = "usage_events"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    session_id = Column(String(255), nullable=True)
    provider = Column(String(50), nullable=False)
    model = Column(String(255), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    credits_used = Column(Float, nullable=False)
    credits_charged = Column(Integer, nullable=False)
    raw_cost_usd = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class CreditTopUp(Base):
    """Record of a credit purchase / add-on pack."""

    __tablename__ = "credit_topups"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False)
    credits = Column(Integer, nullable=False)
    amount_usd = Column(Float, nullable=False)
    payment_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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
        await conn.run_sync(_ensure_user_columns_sync)
    logger.info("Database tables ensured")


def _ensure_user_columns_sync(sync_conn) -> None:
    """Apply lightweight schema fixes for local dev without a migration tool."""
    inspector = inspect(sync_conn)
    if "users" not in inspector.get_table_names():
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "password_hash" not in user_columns:
        sync_conn.execute(text("ALTER TABLE users ADD COLUMN password_hash TEXT"))


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session (for FastAPI dependency injection)."""
    if _session_factory is None:
        raise RuntimeError("Call init_db() before using get_session()")
    async with _session_factory() as session:
        yield session
