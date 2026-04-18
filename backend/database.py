"""PostgreSQL database setup with SQLAlchemy async engine.

Falls back to SQLite when ``DATABASE_URL`` is unset (local development).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    inspect,
    text,
)
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


class ChatSession(Base):
    """Session-v2 record for chat threads with optional parent session."""

    __tablename__ = "chat_sessions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    session_id = Column(String(255), nullable=False, unique=True, index=True)
    parent_session_id = Column(String(255), nullable=True, index=True)
    title = Column(String(500))
    status = Column(String(20), default="active", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ChatSessionMessage(Base):
    """Session-v2 message row associated with a chat session."""

    __tablename__ = "chat_session_messages"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    session_ref_id = Column(String(255), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
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


class Skill(Base):
    """User/admin-submitted skill definition with moderation lifecycle state."""

    __tablename__ = "skills"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    slug = Column(String(120), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    owner_user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    owner_type = Column(String(20), nullable=False, default="user")  # admin|user
    publish_target = Column(String(20), nullable=False, default="hub")  # global|hub
    status = Column(String(40), nullable=False, default="draft")
    visibility = Column(String(20), nullable=False, default="private")
    risk_label = Column(String(20), nullable=False, default="medium")
    created_by = Column(String(255), nullable=True)
    is_new = Column(Boolean, nullable=False, default=False)
    new_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SkillVersion(Base):
    """Immutable version snapshot of a skill submission."""

    __tablename__ = "skill_versions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    skill_id = Column(String(255), ForeignKey("skills.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content_sha256 = Column(String(64), nullable=False, index=True)
    storage_path = Column(Text, nullable=False)
    markdown_content = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=False)
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SkillSubmission(Base):
    """Submission queue record for new skills and updates."""

    __tablename__ = "skill_submissions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    skill_id = Column(String(255), ForeignKey("skills.id"), nullable=False, index=True)
    version_id = Column(String(255), ForeignKey("skill_versions.id"), nullable=False, index=True)
    submitted_by = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    submission_type = Column(String(20), nullable=False, default="new")  # new|update
    review_state = Column(String(40), nullable=False, default="pending_scan")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SkillScanResult(Base):
    """Security/policy scan output for an immutable skill version."""

    __tablename__ = "skill_scan_results"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    skill_version_id = Column(String(255), ForeignKey("skill_versions.id"), nullable=False, index=True)
    engine = Column(String(40), nullable=False)  # virustotal|policy
    verdict = Column(String(30), nullable=False)
    risk_label = Column(String(20), nullable=False, default="low")
    raw_json = Column(Text)
    report_url = Column(Text)
    scanned_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SkillReview(Base):
    """Human moderation decision on a skill version."""

    __tablename__ = "skill_reviews"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    skill_version_id = Column(String(255), ForeignKey("skill_versions.id"), nullable=False, index=True)
    submission_id = Column(String(255), ForeignKey("skill_submissions.id"), nullable=True, index=True)
    reviewer_admin_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    decision = Column(String(40), nullable=False)
    notes = Column(Text)
    reviewed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SkillInstall(Base):
    """Per-user installed skill relation with enabled runtime toggle."""

    __tablename__ = "skill_installs"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_skill_install_user_skill"),)

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    skill_id = Column(String(255), ForeignKey("skills.id"), nullable=False, index=True)
    skill_version_id = Column(String(255), ForeignKey("skill_versions.id"), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    installed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SkillAuditEvent(Base):
    """Immutable audit trail for skill status transitions and key events."""

    __tablename__ = "skill_audit_events"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    skill_id = Column(String(255), ForeignKey("skills.id"), nullable=False, index=True)
    submission_id = Column(String(255), ForeignKey("skill_submissions.id"), nullable=True, index=True)
    skill_version_id = Column(String(255), ForeignKey("skill_versions.id"), nullable=False, index=True)
    from_status = Column(String(40), nullable=False)
    to_status = Column(String(40), nullable=False)
    actor_id = Column(String(255), nullable=False, index=True)
    actor_type = Column(String(20), nullable=False)
    event_type = Column(String(40), nullable=False, default="transition")
    reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class SkillHubSubmission(Base):
    """Skill Hub submission revision tracked by deterministic workflow state."""

    __tablename__ = "skill_hub_submissions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    skill_id = Column(String(255), ForeignKey("skills.id"), nullable=True, index=True)
    skill_slug = Column(String(120), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    risk_label = Column(String(30), nullable=False, default="unknown")
    revision = Column(Integer, nullable=False, default=1)
    submitted_by = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    current_state = Column(String(40), nullable=False, default="draft", index=True)
    reviewer_notes_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SkillHubTransition(Base):
    """Immutable transition event for Skill Hub submissions."""

    __tablename__ = "skill_hub_transitions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    submission_id = Column(String(255), ForeignKey("skill_hub_submissions.id"), nullable=False, index=True)
    from_state = Column(String(40), nullable=False)
    to_state = Column(String(40), nullable=False)
    actor_id = Column(String(255), nullable=False, index=True)
    actor_role = Column(String(20), nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class RuntimeSkillInstallation(Base):
    """Lightweight per-user skill installation record for runtime resolution."""

    __tablename__ = "skill_installations"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_skill_installations_user_skill"),)

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    skill_id = Column(String(255), ForeignKey("skills.id"), nullable=False, index=True)
    installed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SkillToggle(Base):
    """Per-user enable/disable state for an installed skill."""

    __tablename__ = "skill_toggles"
    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", name="uq_skill_toggles_user_skill"),
        ForeignKeyConstraint(
            ["user_id", "skill_id"],
            ["skill_installations.user_id", "skill_installations.skill_id"],
            name="fk_skill_toggles_installation",
            ondelete="CASCADE",
        ),
    )

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    skill_id = Column(String(255), ForeignKey("skills.id"), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ImpersonationSession(Base):
    """Track when admins impersonate user accounts."""

    __tablename__ = "impersonation_sessions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    admin_id = Column(String(255), ForeignKey("users.uid"), nullable=False)
    target_user_id = Column(String(255), ForeignKey("users.uid"), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text)


class AgentTask(Base):
    """A cloud agent task spawned from any channel (web, telegram, slack, discord, github)."""

    __tablename__ = "agent_tasks"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    platform = Column(String(50), nullable=False)
    platform_chat_id = Column(String(255), nullable=True)
    platform_message_id = Column(String(255), nullable=True)
    instruction = Column(Text, nullable=False)
    status = Column(String(30), default="pending")
    agent_type = Column(String(50), default="navigator")
    provider = Column(String(50), nullable=True)
    model = Column(String(255), nullable=True)
    sandbox_id = Column(String(255), nullable=True)
    result_summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    credits_used = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class AgentAction(Base):
    """Individual action performed by a cloud agent during task execution."""

    __tablename__ = "agent_actions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(255), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    action_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    input_data = Column(Text, nullable=True)
    output_data = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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
        await conn.run_sync(_ensure_skill_columns_sync)
        await conn.run_sync(_ensure_audit_log_created_at_sync)
        await conn.run_sync(_ensure_scheduled_tasks_table)
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


def _ensure_skill_columns_sync(sync_conn) -> None:
    """Apply lightweight schema fixes for runtime skill scaffolding tables."""
    inspector = inspect(sync_conn)
    table_names = set(inspector.get_table_names())

    if "skills" in table_names:
        skill_columns = {column["name"] for column in inspector.get_columns("skills")}

        def add_skill_column_if_missing(column_name: str, ddl: str) -> None:
            if column_name in skill_columns:
                return
            try:
                sync_conn.execute(text(ddl))
                skill_columns.add(column_name)
            except Exception as exc:  # pragma: no cover - defensive local-dev schema sync
                logger.warning("Skipping skills.%s sync; assuming column already exists or was created concurrently: %s", column_name, exc)
                skill_columns.add(column_name)

        add_skill_column_if_missing("visibility", "ALTER TABLE skills ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'")
        add_skill_column_if_missing("created_by", "ALTER TABLE skills ADD COLUMN created_by VARCHAR(255)")

    if "skill_versions" in table_names:
        version_columns = {column["name"] for column in inspector.get_columns("skill_versions")}
        if "markdown_content" not in version_columns:
            try:
                sync_conn.execute(text("ALTER TABLE skill_versions ADD COLUMN markdown_content TEXT"))
            except Exception as exc:  # pragma: no cover - defensive local-dev schema sync
                logger.warning(
                    "Skipping skill_versions.markdown_content sync; assuming column already exists or was created concurrently: %s",
                    exc,
                )


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


class UserConnection(Base):
    """OAuth2 connection between a user and an external service (connector)."""

    __tablename__ = "user_connections"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    connector_id = Column(String(50), nullable=False, index=True)  # google, github, slack, etc.
    access_token_enc = Column(Text, nullable=False)  # Fernet-encrypted access token
    refresh_token_enc = Column(Text, nullable=True)  # Fernet-encrypted refresh token
    token_type = Column(String(50), default="Bearer")
    scope = Column(Text, default="")
    expires_at = Column(DateTime(timezone=True), nullable=True)
    account_email = Column(String(320), nullable=True)  # Connected account email/username
    account_name = Column(String(255), nullable=True)  # Display name from the service
    account_avatar = Column(Text, nullable=True)
    raw_metadata = Column(Text, nullable=True)  # JSON blob of extra auth response data
    status = Column(String(20), default="active")  # active | expired | revoked
    connected_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


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


class TaskPlan(Base):
    """A decomposed task plan from a user prompt."""

    __tablename__ = "task_plans"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    conversation_id = Column(String(255), ForeignKey("conversations.id"), nullable=True)
    original_prompt = Column(Text, nullable=False)
    title = Column(String(500), nullable=False)
    status = Column(String(20), default="draft")
    provider = Column(String(50))
    model = Column(String(100))
    plan_json = Column(Text, nullable=False)
    result_summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))


class TaskStep(Base):
    """Individual step within a task plan."""

    __tablename__ = "task_steps"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    plan_id = Column(String(255), ForeignKey("task_plans.id"), nullable=False, index=True)
    parent_step_id = Column(String(255), ForeignKey("task_steps.id"), nullable=True)
    step_index = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    status = Column(String(20), default="pending")
    assigned_provider = Column(String(50))
    assigned_model = Column(String(100))
    depends_on = Column(Text)
    result_text = Column(Text)
    error_message = Column(Text)
    tokens_used = Column(Integer, default=0)
    credits_used = Column(Float, default=0.0)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OAuthAppCredential(Base):
    """Global OAuth app credential (client_id/secret) stored by an admin."""

    __tablename__ = "oauth_app_credentials"

    connector_id = Column(String(50), primary_key=True)  # google, github, slack, etc.
    client_id_enc = Column(Text, nullable=False)         # Fernet-encrypted client_id
    client_secret_enc = Column(Text, nullable=False)     # Fernet-encrypted client_secret
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OAuthPendingState(Base):
    """Short-lived CSRF state token for OAuth flows.

    Stored in the DB instead of (or in addition to) the session cookie so that
    the state survives cross-site redirects where SameSite=Lax blocks cookie
    transmission (e.g. Notion's OAuth server redirects through api.notion.com).
    Expires after 10 minutes.
    """

    __tablename__ = "oauth_pending_states"

    state_token = Column(String(64), primary_key=True)
    connector_id = Column(String(50), nullable=False)
    user_id = Column(String(255), nullable=True)          # None for unauthenticated installs
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PlatformSetting(Base):
    """Key-value store for platform-wide admin-controlled settings.

    Currently used for:
      - ``aegis_global_system_instruction``: injected at the top of every
        agent system prompt (authoritative, users cannot override).
    """

    __tablename__ = "platform_settings"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    updated_by = Column(String(255), nullable=True)  # admin uid who last changed it


class WorkspaceFileGlobal(Base):
    """Admin-managed global workspace-file defaults."""

    __tablename__ = "workspace_files_global"

    name = Column(String(255), primary_key=True)
    content = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    updated_by = Column(String(255), ForeignKey("users.uid"), nullable=True, index=True)


class WorkspaceFileUser(Base):
    """Per-user workspace-file overrides layered over global defaults."""

    __tablename__ = "workspace_files_user"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_workspace_files_user_user_name"),)

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    content = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    updated_by = Column(String(255), ForeignKey("users.uid"), nullable=True, index=True)


class WorkspaceFileAuditEvent(Base):
    """Immutable audit event for workspace-file mutations across scopes."""

    __tablename__ = "workspace_file_audit_events"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    actor_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    scope = Column(String(20), nullable=False)  # global | user
    operation = Column(String(20), nullable=False)  # write | edit | patch | delete
    file_name = Column(String(255), nullable=False, index=True)
    diff_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)


class ScheduledTask(Base):
    """A user-defined cron job that runs an agent prompt on a schedule."""

    __tablename__ = "scheduled_tasks"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    prompt = Column(Text, nullable=False)           # the agent instruction to run
    cron_expr = Column(String(100), nullable=False)  # e.g. "0 9 * * 1" (every Monday 9am)
    timezone = Column(String(100), default="UTC")
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String(20), default="pending")  # pending | running | success | failed
    last_error = Column(Text, nullable=True)
    run_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MemoryEntry(Base):
    """A persistent memory fragment for a user."""

    __tablename__ = "memory_entries"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    category = Column(String(50), default="general")
    source = Column(String(50), default="conversation")
    source_conversation_id = Column(String(255), nullable=True)
    embedding = Column(Text, nullable=True)
    embedding_model = Column(String(100), nullable=True)
    importance = Column(Float, default=0.5)
    access_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    is_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Artifact(Base):
    """A generated artifact from task execution."""

    __tablename__ = "artifacts"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    conversation_id = Column(String(255), ForeignKey("conversations.id"), nullable=True)
    plan_id = Column(String(255), nullable=True)
    step_id = Column(String(255), nullable=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    artifact_type = Column(String(50), nullable=False)
    mime_type = Column(String(200), nullable=False)
    filename = Column(String(500), nullable=False)
    file_size = Column(Integer, default=0)
    storage_path = Column(Text, nullable=False)
    content_preview = Column(Text)
    metadata_json = Column(Text)
    is_pinned = Column(Boolean, default=False)
    download_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ResearchSession(Base):
    """A deep research session with iterative search and synthesis."""

    __tablename__ = "research_sessions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    conversation_id = Column(String(255), ForeignKey("conversations.id"), nullable=True)
    topic = Column(Text, nullable=False)
    status = Column(String(20), default="planning")
    research_plan = Column(Text)
    sources_json = Column(Text)
    findings_json = Column(Text)
    report_artifact_id = Column(String(255), nullable=True)
    total_sources = Column(Integer, default=0)
    total_queries = Column(Integer, default=0)
    queries_completed = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    credits_used = Column(Float, default=0.0)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class BackgroundTask(Base):
    """A queued or running background task."""

    __tablename__ = "background_tasks"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    task_type = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    status = Column(String(20), default="queued", index=True)
    priority = Column(Integer, default=5)
    payload_json = Column(Text, nullable=False)
    result_json = Column(Text)
    error_message = Column(Text)
    progress_pct = Column(Integer, default=0)
    progress_message = Column(String(500))
    max_retries = Column(Integer, default=3)
    retry_count = Column(Integer, default=0)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    notification_sent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


def _ensure_scheduled_tasks_table(sync_conn) -> None:
    """Ensure the scheduled_tasks table has all required columns (idempotent)."""
    inspector = inspect(sync_conn)
    if "scheduled_tasks" not in inspector.get_table_names():
        return  # table was just created by create_all; nothing to migrate

    existing = {col["name"] for col in inspector.get_columns("scheduled_tasks")}

    migrations = [
        ("description", "ALTER TABLE scheduled_tasks ADD COLUMN description TEXT"),
        ("timezone", "ALTER TABLE scheduled_tasks ADD COLUMN timezone VARCHAR(100) DEFAULT 'UTC'"),
        ("enabled", "ALTER TABLE scheduled_tasks ADD COLUMN enabled BOOLEAN DEFAULT TRUE"),
        ("last_run_at", "ALTER TABLE scheduled_tasks ADD COLUMN last_run_at TIMESTAMP WITH TIME ZONE"),
        ("next_run_at", "ALTER TABLE scheduled_tasks ADD COLUMN next_run_at TIMESTAMP WITH TIME ZONE"),
        ("last_status", "ALTER TABLE scheduled_tasks ADD COLUMN last_status VARCHAR(20) DEFAULT 'pending'"),
        ("last_error", "ALTER TABLE scheduled_tasks ADD COLUMN last_error TEXT"),
        ("run_count", "ALTER TABLE scheduled_tasks ADD COLUMN run_count INTEGER DEFAULT 0"),
    ]
    for col_name, ddl in migrations:
        if col_name not in existing:
            try:
                sync_conn.execute(text(ddl))
                existing.add(col_name)
            except Exception as exc:
                logger.warning(
                    "Skipping scheduled_tasks.%s sync; assuming already exists: %s", col_name, exc
                )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session (for FastAPI dependency injection)."""
    if _session_factory is None:
        raise RuntimeError("Call init_db() before using get_session()")
    if not _database_ready:
        raise HTTPException(status_code=503, detail="Database is still initializing")
    async with _session_factory() as session:
        yield session
