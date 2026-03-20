"""PostgreSQL database setup with SQLAlchemy async engine.

Falls back to SQLite when ``DATABASE_URL`` is unset (local development).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
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
    role = Column(String(20), default="user")
    status = Column(String(20), default="active")
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


class Conversation(Base):
    """Persistent conversation record across all platforms."""

    __tablename__ = "conversations"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    platform = Column(String(50), nullable=False)
    platform_chat_id = Column(String(255))
    title = Column(String(500))
    status = Column(String(20), default="active", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ConversationMessage(Base):
    """Individual message within a conversation."""

    __tablename__ = "conversation_messages"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    conversation_id = Column(String(255), ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    platform_message_id = Column(String(255))
    metadata_json = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PaymentMethod(Base):
    """Stored payment method for a user."""

    __tablename__ = "payment_methods"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    stripe_customer_id = Column(String(255))
    stripe_payment_method_id = Column(String(255))
    type = Column(String(30))
    brand = Column(String(30))
    last4 = Column(String(4))
    exp_month = Column(Integer)
    exp_year = Column(Integer)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Immutable log of all admin actions."""

    __tablename__ = "audit_logs"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    admin_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    action = Column(String(100), nullable=False)
    target_user_id = Column(String(255), index=True)
    details_json = Column(Text)
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class ImpersonationSession(Base):
    """Track when admins impersonate user accounts."""

    __tablename__ = "impersonation_sessions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    admin_id = Column(String(255), ForeignKey("users.uid"), nullable=False)
    target_user_id = Column(String(255), ForeignKey("users.uid"), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text)


# ── engine management ─────────────────────────────────────────────────

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_database_ready = False


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
    global _engine, _session_factory, _database_ready

    if database_url:
        url = _resolve_url(database_url)
    else:
        url = "sqlite+aiosqlite:///./aegis_dev.db"
        logger.warning("DATABASE_URL not set — using local SQLite at ./aegis_dev.db")

    _engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    _database_ready = False


async def create_tables() -> None:
    """Create all tables if they don't exist."""
    global _database_ready
    if _engine is None:
        raise RuntimeError("Call init_db() before create_tables()")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_user_columns_sync)
        await conn.run_sync(_ensure_audit_log_created_at_sync)
    _database_ready = True
    logger.info("Database tables ensured")


def _ensure_user_columns_sync(sync_conn) -> None:
    """Apply lightweight schema fixes for local dev without a migration tool."""
    inspector = inspect(sync_conn)
    if "users" not in inspector.get_table_names():
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}

    def add_column_if_missing(column_name: str, ddl: str) -> None:
        if column_name in user_columns:
            return
        try:
            sync_conn.execute(text(ddl))
            user_columns.add(column_name)
        except Exception as exc:  # pragma: no cover - defensive local-dev schema sync
            logger.warning("Skipping users.%s sync; assuming column already exists or was created concurrently: %s", column_name, exc)
            user_columns.add(column_name)

    add_column_if_missing("password_hash", "ALTER TABLE users ADD COLUMN password_hash TEXT")
    add_column_if_missing("role", "ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user'")
    add_column_if_missing("status", "ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT 'active'")


def _ensure_audit_log_created_at_sync(sync_conn) -> None:
    """Backfill missing audit timestamps so ordering and filters remain stable."""
    inspector = inspect(sync_conn)
    if "audit_logs" not in inspector.get_table_names():
        return

    audit_log_columns = {column["name"]: column for column in inspector.get_columns("audit_logs")}
    created_at_column = audit_log_columns.get("created_at")
    if not created_at_column:
        return

    null_count = sync_conn.execute(text("SELECT COUNT(*) FROM audit_logs WHERE created_at IS NULL")).scalar()
    if not null_count:
        return

    try:
        sync_conn.execute(text("UPDATE audit_logs SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
    except Exception as exc:  # pragma: no cover - defensive local-dev schema sync
        logger.warning("Skipping audit_logs.created_at backfill; assuming another startup already repaired it: %s", exc)


class SupportThread(Base):
    """A support / 'Talk to us' conversation between a customer and admin team."""

    __tablename__ = "support_threads"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    subject = Column(String(500), nullable=False)
    status = Column(String(20), default="open", index=True)  # open | resolved | closed
    priority = Column(String(20), default="normal")  # low | normal | high | urgent
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SupportMessage(Base):
    """Individual message within a support thread."""

    __tablename__ = "support_messages"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    thread_id = Column(String(255), ForeignKey("support_threads.id"), nullable=False, index=True)
    sender_id = Column(String(255), ForeignKey("users.uid"), nullable=False)
    sender_role = Column(String(20), nullable=False)  # user | admin | system
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session (for FastAPI dependency injection)."""
    if _session_factory is None:
        raise RuntimeError("Call init_db() before using get_session()")
    if not _database_ready:
        raise HTTPException(status_code=503, detail="Database is still initializing")
    async with _session_factory() as session:
        yield session
