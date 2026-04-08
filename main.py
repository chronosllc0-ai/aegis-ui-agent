"""Aegis UI Navigator - FastAPI entrypoint."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
from http.cookies import SimpleCookie
import json
import logging
from pathlib import Path
import time as _time
from typing import Any
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from aegis_logging import setup_logging
from auth import router as auth_router, _verify_session
from backend.admin import admin_router
from backend import database
from backend.automation import automation_router
from backend.agent_spawn import create_agent_task, get_task_actions, get_task_by_id, get_user_tasks, update_task_status
from backend.artifacts.router import artifact_router
from backend.connectors.router import connector_router
from backend.integrations.text_normalization import normalize_for_channel
from backend.gallery.router import gallery_router
from backend.memory.router import memory_router
from backend.modes import MODE_LABELS, blocked_tools_for_mode, mode_definitions, normalize_agent_mode, serialize_mode_definition
from backend.payments import payments_router
from backend.planner.executor_routes import executor_router
from backend.planner.router import planner_router
from backend.research.router import research_router
from backend.skills.router import skills_router
from backend.skills_hub.router import skills_hub_router
from backend.skills.runtime import resolve_runtime_skills
from backend.tasks.router import task_router as tasks_router
from backend.tasks.worker import BackgroundWorker
from backend.conversation_service import append_message, get_or_create_conversation
from backend.database import get_session, init_db, create_tables, SupportThread, SupportMessage, UserConnection
from backend.credit_rates import CREDIT_RATES, get_tier
from backend.credit_service import check_credits, get_or_create_balance, get_usage_history, get_usage_summary, record_usage
from backend.key_management import KeyManager
from backend.providers import get_provider, list_providers
from config import settings
from integrations.discord import DiscordIntegration
from integrations.github_connector import GitHubIntegration
from integrations.slack_connector import SlackIntegration
from integrations.telegram import TelegramIntegration
from orchestrator import AgentOrchestrator
from session import LiveSessionManager
from backend.session_workspace import cleanup_session_workspace

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

app = FastAPI(title="Aegis UI Navigator", version="1.0.0")
cors_origins = [origin for origin in {settings.resolved_frontend_url, settings.resolved_public_base_url} if origin]
if settings.CORS_ORIGINS:
    cors_origins.extend([o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()])
if not cors_origins:
    cors_origins = ["http://localhost:5173", "http://localhost:8000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if settings.SESSION_SECRET:
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SESSION_SECRET,
        same_site=settings.normalized_cookie_samesite,
        https_only=bool(settings.COOKIE_SECURE),
        domain=settings.resolved_cookie_domain,
    )
else:
    logger.warning("SESSION_SECRET is not set; OAuth flows will fail without session support.")

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(artifact_router)
app.include_router(automation_router)
app.include_router(connector_router)
app.include_router(gallery_router)
app.include_router(memory_router)
app.include_router(payments_router)
app.include_router(planner_router)
app.include_router(executor_router)
app.include_router(research_router)
app.include_router(tasks_router)
app.include_router(skills_router)
app.include_router(skills_hub_router)

orchestrator: AgentOrchestrator | None = None
live_manager = LiveSessionManager()
key_manager = KeyManager(settings.ENCRYPTION_SECRET)
db_init_task: asyncio.Task[None] | None = None
db_init_error: str | None = None
db_ready = False
background_worker = BackgroundWorker(max_concurrent=3, poll_interval=5.0)

FRONTEND_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"


# ── Database lifecycle ────────────────────────────────────────────────


async def _initialize_database() -> None:
    """Initialize the database with retries without blocking app readiness."""
    global db_ready, db_init_error

    configured_database_url = settings.DATABASE_URL or None
    attempted_sqlite_fallback = False
    retry_delay_seconds = 5
    while True:
        try:
            init_db(configured_database_url)
            await create_tables()
        except Exception as exc:  # noqa: BLE001
            if _should_fallback_to_local_sqlite(configured_database_url, exc) and not attempted_sqlite_fallback:
                logger.warning(
                    "Database initialization failed for local DATABASE_URL; falling back to SQLite. error=%s",
                    exc,
                )
                configured_database_url = None
                attempted_sqlite_fallback = True
                continue
            db_ready = False
            db_init_error = str(exc)
            logger.exception(
                "Database initialization failed; retrying in %s seconds",
                retry_delay_seconds,
            )
            await asyncio.sleep(retry_delay_seconds)
        else:
            db_ready = True
            db_init_error = None
            logger.info("Database initialized")
            # Auto-seed superadmin if env vars are set
            if settings.SUPERADMIN_EMAIL and settings.SUPERADMIN_PASSWORD:
                try:
                    from scripts.seed_super_admin import seed_super_admin
                    result = await seed_super_admin(
                        email=settings.SUPERADMIN_EMAIL,
                        password=settings.SUPERADMIN_PASSWORD,
                        name=settings.SUPERADMIN_NAME or "Super Admin",
                        database_url=configured_database_url,
                    )
                    action = "created" if result.get("created") else "updated"
                    logger.info("Superadmin %s: %s", action, result.get("email"))
                except Exception as seed_exc:  # noqa: BLE001
                    logger.warning("Superadmin seed failed (non-fatal): %s", seed_exc)
            return


def _should_fallback_to_local_sqlite(database_url: str | None, exc: Exception) -> bool:
    """Return whether local dev should fall back to SQLite after a PostgreSQL failure."""
    if not database_url or settings.RAILWAY_ENVIRONMENT:
        return False

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        return False
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return False

    error_text = str(exc).lower()
    if isinstance(exc, ModuleNotFoundError):
        return exc.name == "asyncpg" or "asyncpg" in error_text

    return any(
        marker in error_text
        for marker in (
            "connection refused",
            "could not connect",
            "actively refused",
            "connect call failed",
            "timeout expired",
            "timed out",
        )
    )


@app.on_event("startup")
async def startup_event() -> None:
    """Kick off database initialization and cron scheduler on application startup."""
    global db_init_task
    from backend.task_runner import start_scheduler

    if db_init_task is None or db_init_task.done():
        db_init_task = asyncio.create_task(_initialize_database())

    start_scheduler()
    await background_worker.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cancel any outstanding background initialization tasks."""
    global db_init_task

    if db_init_task is not None and not db_init_task.done():
        db_init_task.cancel()
        try:
            await db_init_task
        except asyncio.CancelledError:
            logger.info("Database initialization task cancelled during shutdown")
    await background_worker.stop()


# ── Auth helper ───────────────────────────────────────────────────────


def _extract_session_user_uid(token: str | None) -> str | None:
    """Extract user UID from a session token string."""
    payload = _verify_session(token)
    return payload["uid"] if payload else None


def _extract_websocket_user_uid(websocket: WebSocket) -> str | None:
    """Extract user UID from a WebSocket connection's session cookie."""
    cookie_header = websocket.headers.get("cookie", "")
    jar = SimpleCookie()
    jar.load(cookie_header)
    token = jar["aegis_session"].value if "aegis_session" in jar else None
    return _extract_session_user_uid(token)


def _get_current_user(request: Request) -> dict[str, Any]:
    """Extract the authenticated user from the session cookie."""
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload


# ── Integration registries ────────────────────────────────────────────


class TelegramRegistry:
    """In-memory telegram integration registry for webhook routing."""

    def __init__(self) -> None:
        self._integrations: dict[str, TelegramIntegration] = {}
        self._configs: dict[str, dict[str, Any]] = {}

    def get_telegram(self, integration_id: str) -> TelegramIntegration | None:
        return self._integrations.get(integration_id)

    def get_config(self, integration_id: str) -> dict[str, Any]:
        return self._configs.get(integration_id, {})

    def upsert(self, integration_id: str, integration: TelegramIntegration, config: dict[str, Any]) -> None:
        self._integrations[integration_id] = integration
        self._configs[integration_id] = config


telegram_registry = TelegramRegistry()


class SlackRegistry:
    """In-memory slack integration registry."""

    def __init__(self) -> None:
        self._integrations: dict[str, SlackIntegration] = {}
        self._configs: dict[str, dict[str, Any]] = {}

    def get_slack(self, integration_id: str) -> SlackIntegration | None:
        return self._integrations.get(integration_id)

    def get_config(self, integration_id: str) -> dict[str, Any]:
        return self._configs.get(integration_id, {})

    def upsert(self, integration_id: str, integration: SlackIntegration, config: dict[str, Any]) -> None:
        self._integrations[integration_id] = integration
        self._configs[integration_id] = config


class DiscordRegistry:
    """In-memory discord integration registry."""

    def __init__(self) -> None:
        self._integrations: dict[str, DiscordIntegration] = {}
        self._configs: dict[str, dict[str, Any]] = {}

    def get_discord(self, integration_id: str) -> DiscordIntegration | None:
        return self._integrations.get(integration_id)

    def get_config(self, integration_id: str) -> dict[str, Any]:
        return self._configs.get(integration_id, {})

    def upsert(self, integration_id: str, integration: DiscordIntegration, config: dict[str, Any]) -> None:
        self._integrations[integration_id] = integration
        self._configs[integration_id] = config


class GitHubRegistry:
    """In-memory github integration registry."""

    def __init__(self) -> None:
        self._integrations: dict[str, GitHubIntegration] = {}
        self._configs: dict[str, dict[str, Any]] = {}

    def get_github(self, integration_id: str) -> GitHubIntegration | None:
        return self._integrations.get(integration_id)

    def get_config(self, integration_id: str) -> dict[str, Any]:
        return self._configs.get(integration_id, {})

    def upsert(self, integration_id: str, integration: GitHubIntegration, config: dict[str, Any]) -> None:
        self._integrations[integration_id] = integration
        self._configs[integration_id] = config


slack_registry = SlackRegistry()
discord_registry = DiscordRegistry()
github_registry = GitHubRegistry()

# Maps authenticated user_uid -> active SessionRuntime (for bot command bridging)
_user_runtimes: dict[str, "SessionRuntime"] = {}

# Stream subscribers: user_uid -> {platform, integration_id, chat_id, last_sent_at}
_stream_subscribers: dict[str, dict[str, Any]] = {}

# Bot config: integration_id -> config dict
_bot_configs: dict[str, dict[str, Any]] = {}


def _apply_runtime_mode_update(
    runtime: SessionRuntime,
    requested_mode_raw: object,
    *,
    apply: bool = True,
) -> tuple[str, bool, str | None]:
    """Validate/apply requested mode for a runtime and return outcome details."""
    requested_mode, mode_valid = validate_requested_mode(requested_mode_raw)
    if mode_valid and apply:
        runtime.settings["agent_mode"] = requested_mode
        return requested_mode, True, None
    allowed = ", ".join(MODE_LABELS.keys())
    return (
        requested_mode,
        False,
        f"Invalid mode `{requested_mode_raw}`. Allowed modes: {allowed}.",
    )


def validate_requested_mode(requested_mode_raw: object) -> tuple[str, bool]:
    """Normalize a raw mode payload and return whether it is an allowed explicit mode."""
    candidate = str(requested_mode_raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if candidate in MODE_LABELS:
        return candidate, True
    return normalize_agent_mode(candidate), False


def _normalize_runtime_mode(runtime_settings: dict[str, Any]) -> str:
    """Normalize the active runtime mode and persist canonical value in settings."""
    normalized = normalize_agent_mode(runtime_settings.get("agent_mode", ""))
    runtime_settings["agent_mode"] = normalized
    return normalized


def allowed_tool_alternatives(mode: str, *, limit: int = 8) -> list[str]:
    """Return representative tools that remain available in the requested mode."""
    blocked = blocked_tools_for_mode(mode)
    candidates = (
        "screenshot",
        "analyze_screen",
        "ask_user_input",
        "memory_search",
        "memory_read",
        "web_search",
        "extract_page",
        "list_files",
        "read_file",
        "done",
        "error",
    )
    return [tool for tool in candidates if tool not in blocked][: max(1, limit)]


def _mode_refusal_payload(*, requested_mode: object, effective_mode: str, reason: str) -> dict[str, Any]:
    """Create a consistent websocket payload for mode-policy refusals."""
    return {
        "type": "mode_policy_refusal",
        "requested_mode": str(requested_mode or ""),
        "effective_mode": effective_mode,
        "reason": reason,
        "allowed_alternatives": allowed_tool_alternatives(effective_mode),
    }


def _get_orchestrator() -> AgentOrchestrator:
    """Return a lazily initialized orchestrator instance."""
    global orchestrator
    if orchestrator is None:
        orchestrator = AgentOrchestrator()
    return orchestrator


class SessionRuntime:
    """In-memory runtime state for a websocket navigation session."""

    def __init__(self) -> None:
        self.task_running = False
        self.current_task: asyncio.Task[None] | None = None
        self.cancel_event = asyncio.Event()
        self.steering_context: list[str] = []
        self.queued_instructions: list[str] = []
        self.settings: dict[str, Any] = {}
        self.conversation_id: str | None = None
        self.user_uid: str | None = None
        # Pending user-input futures keyed by request_id
        self.pending_user_inputs: dict[str, asyncio.Future[str]] = {}
        # Sub-agent manager — created lazily on first spawn
        from subagent_runtime import SubAgentManager
        self.subagent_manager: SubAgentManager = SubAgentManager()


def _merge_runtime_settings(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge websocket config payload with defaults without dropping prior settings."""
    merged = {**current, **incoming}
    provider = str(merged.get("provider", "")).strip().lower()
    if not provider:
        merged["provider"] = "chronos"
    model = str(merged.get("model", "")).strip()
    if not model:
        merged["model"] = "nvidia/nemotron-3-super-120b-a12b:free"
    return merged


# ── Provider & BYOK API routes ────────────────────────────────────────


@app.get("/api/providers")
async def get_providers() -> dict[str, Any]:
    """List all supported LLM providers and their models."""
    return {"ok": True, "providers": list_providers()}


@app.get("/api/modes")
async def get_modes(request: Request) -> dict[str, Any]:
    """Return the canonical immutable mode registry."""
    _get_current_user(request)
    return {"ok": True, "modes": [serialize_mode_definition(mode.key) for mode in mode_definitions()]}


@app.post("/api/modes")
async def create_mode(_: dict[str, Any], request: Request) -> None:
    """Reject mode creation; modes are immutable system-owned nodes."""
    _get_current_user(request)
    raise HTTPException(
        status_code=403,
        detail="Modes are immutable system-level nodes and cannot be created, modified, or deleted via this API.",
    )


@app.patch("/api/modes/{mode_key}")
async def patch_mode(mode_key: str, _: dict[str, Any], request: Request) -> None:
    """Reject mode mutation; protected mode policy fields are immutable."""
    _get_current_user(request)
    _ = mode_key
    raise HTTPException(status_code=403, detail="Protected mode policy fields are immutable")


@app.delete("/api/modes/{mode_key}")
async def delete_mode(mode_key: str, request: Request) -> None:
    """Reject mode deletion; canonical mode registry is fixed."""
    _get_current_user(request)
    _ = mode_key
    raise HTTPException(
        status_code=403,
        detail="Modes are immutable system-level nodes and cannot be created, modified, or deleted via this API.",
    )


@app.get("/api/keys")
async def get_user_keys(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List stored API key hints for the current user."""
    user = _get_current_user(request)
    keys = await key_manager.list_keys(session, user["uid"])
    return {"ok": True, "keys": keys}


@app.post("/api/keys")
async def store_user_key(
    request: Request,
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Store (or update) an encrypted API key for a provider."""
    user = _get_current_user(request)
    provider = str(payload.get("provider", "")).strip()
    api_key = str(payload.get("api_key", "")).strip()
    if not provider or not api_key:
        raise HTTPException(status_code=400, detail="provider and api_key are required")
    result = await key_manager.store_key(session, user["uid"], provider, api_key)
    return {"ok": True, **result}


@app.delete("/api/keys/{provider}")
async def delete_user_key(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Delete a stored API key for a provider."""
    user = _get_current_user(request)
    deleted = await key_manager.delete_key(session, user["uid"], provider)
    if not deleted:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"ok": True, "provider": provider}


# ── Usage / Credit API routes ─────────────────────────────────────────


@app.get("/api/usage/balance")
async def usage_balance(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return current credit balance for the authenticated user."""
    user = _get_current_user(request)
    return await check_credits(session, user["uid"])


@app.get("/api/usage/summary")
async def usage_summary(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return aggregated usage stats for the dashboard."""
    user = _get_current_user(request)
    return await get_usage_summary(session, user["uid"])


@app.get("/api/usage/history")
async def usage_history(
    request: Request,
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Return paginated usage event log."""
    user = _get_current_user(request)
    return await get_usage_history(
        session, user["uid"], limit=limit, offset=offset, provider=provider, model=model
    )


@app.get("/api/usage/rates")
async def usage_rates() -> dict[str, Any]:
    """Return all credit rates for client-side cost estimation."""
    return {"rates": CREDIT_RATES}


@app.put("/api/usage/spending-cap")
async def set_spending_cap(
    request: Request,
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Set or remove the spending cap for the authenticated user."""
    user = _get_current_user(request)
    balance = await get_or_create_balance(session, user["uid"])
    balance.spending_cap = payload.get("cap")
    await session.commit()
    return {"spending_cap": balance.spending_cap}


# ── Customer support messaging ────────────────────────────────────────


@app.get("/api/support/threads")
async def list_my_support_threads(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List the current user's support threads."""
    user = _get_current_user(request)
    result = await session.execute(
        select(SupportThread).where(SupportThread.user_id == user["uid"]).order_by(SupportThread.updated_at.desc())
    )
    threads = result.scalars().all()
    return {
        "threads": [
            {
                "id": t.id,
                "subject": t.subject,
                "status": t.status,
                "priority": t.priority,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in threads
        ]
    }


@app.post("/api/support/threads")
async def create_support_thread(
    request: Request,
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a new support thread (customer opens a conversation)."""
    user = _get_current_user(request)
    subject = (payload.get("subject") or "").strip()
    message = (payload.get("message") or "").strip()
    if not subject or not message:
        raise HTTPException(400, "subject and message are required")
    thread = SupportThread(user_id=user["uid"], subject=subject)
    session.add(thread)
    await session.flush()
    msg = SupportMessage(thread_id=thread.id, sender_id=user["uid"], sender_role="user", content=message)
    session.add(msg)
    await session.commit()
    await session.refresh(thread)
    return {"thread_id": thread.id, "status": "created"}


@app.get("/api/support/threads/{thread_id}")
async def get_support_thread(
    thread_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get messages in a support thread (for the customer)."""
    user = _get_current_user(request)
    result = await session.execute(
        select(SupportThread).where(SupportThread.id == thread_id, SupportThread.user_id == user["uid"])
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(404, "Thread not found")
    msgs = await session.execute(
        select(SupportMessage).where(SupportMessage.thread_id == thread_id).order_by(SupportMessage.created_at.asc())
    )
    messages = msgs.scalars().all()
    return {
        "thread": {"id": thread.id, "subject": thread.subject, "status": thread.status},
        "messages": [
            {
                "id": m.id,
                "sender_role": m.sender_role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@app.post("/api/support/threads/{thread_id}/reply")
async def reply_support_thread(
    thread_id: str,
    request: Request,
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Customer sends a reply in their support thread."""
    user = _get_current_user(request)
    result = await session.execute(
        select(SupportThread).where(SupportThread.id == thread_id, SupportThread.user_id == user["uid"])
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(404, "Thread not found")
    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(400, "content is required")
    msg = SupportMessage(thread_id=thread_id, sender_id=user["uid"], sender_role="user", content=content)
    session.add(msg)
    from datetime import datetime
    thread.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(msg)
    return {
        "message": {
            "id": msg.id,
            "sender_role": "user",
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }
    }


# ── Health check ──────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, str]:
    """Return service health status without failing while dependencies warm up."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "database": "ready" if db_ready else "initializing",
        "database_error": db_init_error or "",
    }


# ── Conversation persistence API ─────────────────────────────────────

@app.get("/api/conversations")
async def list_conversations(
    request: Request,
    limit: int = 50,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return all conversations for the authenticated user (most recent first)."""
    user = _get_current_user(request)
    uid = user["uid"]
    from sqlalchemy import select as sa_select, desc as sa_desc
    from backend.database import Conversation as ConvModel
    stmt = (
        sa_select(ConvModel)
        .where(ConvModel.user_id == uid, ConvModel.platform == "web")
        .order_by(sa_desc(ConvModel.updated_at))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "ok": True,
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in rows
        ],
    }


@app.get("/api/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    request: Request,
    limit: int = 500,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return all messages for a conversation, oldest first. Only accessible by owner."""
    user = _get_current_user(request)
    uid = user["uid"]
    import json as _json
    from sqlalchemy import select as sa_select
    from backend.database import Conversation as ConvModel, ConversationMessage as MsgModel
    # Ownership check
    conv = (await db.execute(sa_select(ConvModel).where(ConvModel.id == conversation_id))).scalar_one_or_none()
    if not conv or conv.user_id != uid:
        raise HTTPException(status_code=404, detail="Conversation not found")
    stmt = (
        sa_select(MsgModel)
        .where(MsgModel.conversation_id == conversation_id)
        .order_by(MsgModel.created_at)
        .limit(limit)
    )
    msgs = (await db.execute(stmt)).scalars().all()
    return {
        "ok": True,
        "conversation": {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
        },
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "metadata": _json.loads(m.metadata_json) if m.metadata_json else None,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ],
    }


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Soft-delete a conversation (sets status=archived)."""
    user = _get_current_user(request)
    uid = user["uid"]
    from sqlalchemy import select as sa_select
    from backend.database import Conversation as ConvModel
    conv = (await db.execute(sa_select(ConvModel).where(ConvModel.id == conversation_id))).scalar_one_or_none()
    if not conv or conv.user_id != uid:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.status = "archived"
    await db.commit()
    return {"ok": True}


# ── WebSocket helpers ─────────────────────────────────────────────────


async def _send_step(
    websocket: WebSocket,
    step: dict[str, Any],
    *,
    runtime: "SessionRuntime | None" = None,
    session_id: str | None = None,
) -> None:
    """Send step payload to frontend."""
    normalized_step = dict(step)
    if "content" in normalized_step:
        normalized_content, _ = normalize_for_channel(str(normalized_step["content"] or ""), channel="web")
        normalized_step["content"] = normalized_content
    await websocket.send_json({"type": "step", "data": normalized_step})
    if runtime and session_id:
        await _log_web_message(
            runtime,
            session_id,
            "assistant",
            str(normalized_step.get("content") or normalized_step.get("type") or "Step update"),
            metadata={"source": "websocket", "action": "step", "step": normalized_step},
        )


async def _send_frame(websocket: WebSocket, image_b64: str) -> None:
    """Send a base64 PNG frame over websocket."""
    await websocket.send_json({"type": "frame", "data": {"image": image_b64}})


async def _send_initial_frame(websocket: WebSocket) -> None:
    """Capture and send an initial frame when the websocket connects.

    Skips sending if the browser is still at about:blank so the frontend can
    display its "Tell me what to do" welcome screen instead of a white frame.
    """
    try:
        executor = _get_orchestrator().executor
        current_url = executor.page.url if executor.page else "about:blank"
        if current_url in ("about:blank", ""):
            return  # Don't replace the welcome screen with a white blank frame
        screenshot_bytes = await executor.screenshot()
        await _send_frame(websocket, base64.b64encode(screenshot_bytes).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Initial frame capture failed: %s", exc)


async def _send_workflow_step(
    websocket: WebSocket,
    workflow_step: dict[str, Any],
    *,
    runtime: "SessionRuntime | None" = None,
    session_id: str | None = None,
) -> None:
    """Send workflow graph step payload to frontend."""
    await websocket.send_json({"type": "workflow_step", "data": workflow_step})
    if runtime and session_id:
        await _log_web_message(
            runtime,
            session_id,
            "assistant",
            str(workflow_step.get("description") or workflow_step.get("action") or "Workflow step update"),
            metadata={"source": "websocket", "action": "workflow_step", "workflow_step": workflow_step},
        )


async def _send_transcript(websocket: WebSocket, text: str, source: str = "voice") -> None:
    """Send a transcript payload to the frontend."""
    await websocket.send_json({"type": "transcript", "data": {"text": text, "source": source}})


async def _send_context_update(
    websocket: WebSocket,
    tokens_used: int,
    context_limit: int,
    compacting: bool = False,
    *,
    runtime: "SessionRuntime | None" = None,
    session_id: str | None = None,
) -> None:
    """Push a context-window usage update to the frontend meter."""
    await websocket.send_json({
        "type": "context_update",
        "tokens_used": tokens_used,
        "context_limit": context_limit,
        "compacting": compacting,
    })
    if runtime and session_id:
        await _log_web_message(
            runtime,
            session_id,
            "assistant",
            f"Context usage {tokens_used}/{context_limit}",
            metadata={
                "source": "websocket",
                "action": "context_update",
                "tokens_used": tokens_used,
                "context_limit": context_limit,
                "compacting": compacting,
            },
        )


async def _log_web_message(
    runtime: "SessionRuntime",
    session_id: str,
    role: str,
    content: str,
    *,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
    title_candidate: str | None = None,
) -> None:
    """Persist a websocket message to the conversations DB and emit conversation_id to client."""
    if not runtime.user_uid:
        return
    try:
        async for db in get_session():
            conv = await get_or_create_conversation(
                db,
                user_id=runtime.user_uid,
                platform="web",
                platform_chat_id=session_id,
                title=title,
            )
            runtime.conversation_id = conv.id
            await append_message(
                db,
                conv.id,
                role,
                content,
                metadata=metadata,
                title_candidate=title_candidate,
            )
            break
    except Exception:  # noqa: BLE001
        logger.warning("Failed to persist web message to DB for session %s", session_id)


async def _on_frame_combined(websocket: WebSocket, image_b64: str, user_uid: str | None) -> None:
    """Send frame to websocket AND any active stream subscribers (rate-limited)."""
    await _send_frame(websocket, image_b64)
    if not user_uid:
        return
    sub = _stream_subscribers.get(user_uid)
    if not sub:
        return
    now = _time.monotonic()
    if now - sub.get("last_sent_at", 0) < 3.0:
        return  # rate limit: max 1 frame per 3 seconds
    sub["last_sent_at"] = now
    platform = sub.get("platform")
    integration_id = sub.get("integration_id")
    chat_id = sub.get("chat_id")
    if platform == "telegram":
        integration = telegram_registry.get_telegram(integration_id)
        if integration:
            asyncio.create_task(
                integration.send_photo(chat_id, image_b64)
            )
    elif platform == "discord":
        integration = discord_registry.get_discord(integration_id)
        if integration:
            channel = sub.get("channel_id", chat_id)
            asyncio.create_task(
                integration.send_image(channel, image_b64)
            )


def _start_navigation_task(websocket: WebSocket, runtime: SessionRuntime, session_id: str, instruction: str) -> None:
    """Create and store the background navigation task for the current session."""
    runtime.current_task = asyncio.create_task(_run_navigation_task(websocket, runtime, session_id, instruction))


async def _start_idle_navigation_from_control_action(
    websocket: WebSocket,
    runtime: SessionRuntime,
    session_id: str,
    instruction: str,
    *,
    action: str,
    task_label: str,
    title_candidate: str,
    client_metadata: dict[str, Any] | None,
) -> None:
    """Treat control actions as fresh task starts when the runtime is idle."""
    await _log_web_message(
        runtime,
        session_id,
        "user",
        instruction,
        title=instruction[:200],
        title_candidate=title_candidate,
        metadata={
            "source": "websocket",
            "action": f"navigate_from_idle_{action}",
            "task_label": task_label,
            "client": client_metadata or {},
        },
    )
    if runtime.conversation_id:
        await websocket.send_json({"type": "conversation_id", "data": {"conversation_id": runtime.conversation_id}})
    _start_navigation_task(websocket, runtime, session_id, instruction)


async def _start_next_queued_task_if_ready(websocket: WebSocket, runtime: SessionRuntime, session_id: str) -> None:
    """Start the next queued task when no task is active and cancellation is not pending."""
    if runtime.task_running or runtime.cancel_event.is_set() or not runtime.queued_instructions:
        return

    queued_instruction = runtime.queued_instructions.pop(0)
    await _send_step(
        websocket,
        {
            "type": "queue",
            "content": f"Starting queued task: {queued_instruction}",
        },
        runtime=runtime,
        session_id=session_id,
    )
    await _log_web_message(
        runtime,
        session_id,
        "user",
        queued_instruction,
        title=queued_instruction[:200],
        metadata={"source": "websocket", "action": "queue"},
    )
    _start_navigation_task(websocket, runtime, session_id, queued_instruction)


async def _run_navigation_task(
    websocket: WebSocket,
    runtime: SessionRuntime,
    session_id: str,
    instruction: str,
) -> None:
    """Execute a single navigation task and optionally schedule one queued follow-up."""
    callback: Callable[[dict[str, Any]], Awaitable[None]] = lambda step: _send_step(
        websocket,
        step,
        runtime=runtime,
        session_id=session_id,
    )
    runtime.task_running = True
    runtime.cancel_event.clear()
    _normalize_runtime_mode(runtime.settings)

    async def _on_user_input(question: str, options: list[str]) -> str:
        """Send a user_input_request WS message and await the user's response."""
        import uuid as _uuid
        request_id = str(_uuid.uuid4())
        fut: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        runtime.pending_user_inputs[request_id] = fut
        try:
            await websocket.send_json({
                "type": "step",
                "data": {
                    "type": "user_input_request",
                    "content": f"[ask_user_input] {question}",
                    "question": question,
                    "options": options,
                    "request_id": request_id,
                },
            })
            return await asyncio.wait_for(fut, timeout=300.0)
        except asyncio.TimeoutError:
            return "No response (timed out)."
        finally:
            runtime.pending_user_inputs.pop(request_id, None)

    async def _on_reasoning_delta(step_id: str, delta_text: str) -> None:
        normalized_delta, _ = normalize_for_channel(delta_text, channel="web")
        await websocket.send_json({
            "type": "reasoning_delta",
            "data": {
                "step_id": step_id,
                "delta": normalized_delta,
            },
        })

    async def _on_spawn_subagent(sub_instruction: str, sub_model: str) -> str:
        """Spawn a sub-agent on behalf of the main agent and return its sub_id."""
        effective_model = sub_model or str(runtime.settings.get("model", "nvidia/nemotron-3-super-120b-a12b")).strip()

        async def _sub_send(msg: dict[str, Any]) -> None:
            try:
                await websocket.send_json(msg)
            except Exception:  # noqa: BLE001
                pass

        sub_id = await runtime.subagent_manager.spawn(
            instruction=sub_instruction,
            model=effective_model,
            parent_user_uid=runtime.user_uid,
            orchestrator=_get_orchestrator(),
            parent_settings=runtime.settings,
            send_to_parent=_sub_send,
            on_user_input=None,
        )
        # Send updated agent list to frontend
        await websocket.send_json({
            "type": "subagent_list",
            "data": {"agents": runtime.subagent_manager.list_agents()},
        })
        return sub_id

    async def _on_message_subagent(sub_id: str, message: str) -> bool:
        return await runtime.subagent_manager.send_message(sub_id, message)

    try:
        result = await _get_orchestrator().execute_task(
            session_id=session_id,
            instruction=instruction,
            on_step=callback,
            on_frame=lambda image_b64: _on_frame_combined(websocket, image_b64, runtime.user_uid),
            cancel_event=runtime.cancel_event,
            steering_context=runtime.steering_context,
            settings=runtime.settings,
            on_workflow_step=lambda step: _send_workflow_step(
                websocket,
                step,
                runtime=runtime,
                session_id=session_id,
            ),
            user_uid=runtime.user_uid,
            on_user_input=_on_user_input,
            on_reasoning_delta=_on_reasoning_delta,
            on_spawn_subagent=_on_spawn_subagent,
            on_message_subagent=_on_message_subagent,
        )
        result_status = result.get("status") if isinstance(result, dict) else "completed"

        # ── Chronos Gateway credit recording ──────────────────────────
        if (
            isinstance(result, dict)
            and runtime.settings.get("provider") == "chronos"
            and runtime.user_uid
        ):
            input_tokens = result.get("input_tokens", 0)
            output_tokens = result.get("output_tokens", 0)
            model_id = runtime.settings.get("model", "nvidia/nemotron-3-super-120b-a12b:free")
            if input_tokens or output_tokens:
                try:
                    async for _db_session in get_session():
                        await record_usage(
                            _db_session,
                            runtime.user_uid,
                            "chronos",
                            model_id,
                            input_tokens,
                            output_tokens,
                            session_id=session_id,
                        )
                        await _db_session.commit()
                        break
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to record Chronos Gateway usage for user %s", runtime.user_uid)

        # If execute_task returned a failure (e.g. unsupported provider), surface it as an error
        if result_status == "failed":
            error_msg = (result.get("error") or "Task failed") if isinstance(result, dict) else "Task failed"
            await websocket.send_json({"type": "error", "data": {"message": error_msg}})
        await _log_web_message(
            runtime,
            session_id,
            "assistant",
            f"Task {result_status}: {instruction}",
            metadata={
                "source": "websocket",
                "action": "result",
                "status": result_status,
                "result": result if isinstance(result, dict) else str(result),
            },
        )
        await websocket.send_json({"type": "result", "data": result})
    except asyncio.CancelledError:
        logger.info("Navigation task cancelled for session %s", session_id)
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Navigation task failed for session %s", session_id)
        await _log_web_message(
            runtime,
            session_id,
            "assistant",
            f"Task failed: {instruction}",
            metadata={
                "source": "websocket",
                "action": "result",
                "status": "failed",
                "error": str(exc),
            },
        )
        await websocket.send_json({"type": "error", "data": {"message": str(exc)}})
        await websocket.send_json({"type": "result", "data": {"status": "failed", "instruction": instruction, "steps": []}})
    finally:
        runtime.task_running = False

    await _start_next_queued_task_if_ready(websocket, runtime, session_id)


# ── WebSocket navigation endpoint ────────────────────────────────────


@app.websocket("/ws/navigate")
async def websocket_navigate(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time UI navigation sessions."""
    await websocket.accept()
    session_id = await live_manager.create_session()
    runtime = SessionRuntime()
    runtime.user_uid = _extract_websocket_user_uid(websocket)
    if runtime.user_uid:
        _user_runtimes[runtime.user_uid] = runtime

    try:
        await _get_orchestrator().executor.ensure_browser()
        await _send_initial_frame(websocket)

        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            instruction = str(data.get("instruction", "")).strip()
            requested_mode_raw = data.get("mode")
            if requested_mode_raw is not None:
                requested_mode, mode_valid, _ = _apply_runtime_mode_update(runtime, requested_mode_raw)
                if not mode_valid:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": _mode_refusal_payload(
                                requested_mode=requested_mode_raw,
                                effective_mode=requested_mode,
                                reason="invalid_mode",
                            ),
                        }
                    )
                    continue
            active_mode = _normalize_runtime_mode(runtime.settings)
            raw_metadata = data.get("metadata")
            client_metadata = raw_metadata if isinstance(raw_metadata, dict) else None
            task_label = str(client_metadata.get("task_label", "")).strip() if client_metadata else ""
            title_candidate = task_label or instruction

            if action == "navigate":
                if runtime.task_running:
                    await websocket.send_json({"type": "error", "data": {"message": "Task already running"}})
                    continue
                await _log_web_message(
                    runtime,
                    session_id,
                    "user",
                    instruction,
                    title=instruction[:200],
                    title_candidate=title_candidate,
                    metadata={
                        "source": "websocket",
                        "action": "navigate",
                        "task_label": task_label,
                        "client": client_metadata or {},
                    },
                )
                if runtime.conversation_id:
                    await websocket.send_json({"type": "conversation_id", "data": {"conversation_id": runtime.conversation_id}})
                _start_navigation_task(websocket, runtime, session_id, instruction)
            elif action == "steer":
                if not runtime.task_running:
                    await _start_idle_navigation_from_control_action(
                        websocket,
                        runtime,
                        session_id,
                        instruction,
                        action="steer",
                        task_label=task_label,
                        title_candidate=title_candidate,
                        client_metadata=client_metadata,
                    )
                    continue
                runtime.steering_context.append(instruction)
                await _send_step(
                    websocket,
                    {"type": "steer", "content": f"Steering note added: {instruction}"},
                    runtime=runtime,
                    session_id=session_id,
                )
                await _log_web_message(
                    runtime,
                    session_id,
                    "user",
                    instruction,
                    metadata={"source": "websocket", "action": "steer", "client": client_metadata or {}},
                )
            elif action == "interrupt":
                if not runtime.task_running:
                    await _start_idle_navigation_from_control_action(
                        websocket,
                        runtime,
                        session_id,
                        instruction,
                        action="interrupt",
                        task_label=task_label,
                        title_candidate=title_candidate,
                        client_metadata=client_metadata,
                    )
                    continue
                runtime.cancel_event.set()
                await _send_step(
                    websocket,
                    {"type": "interrupt", "content": "Task interrupted"},
                    runtime=runtime,
                    session_id=session_id,
                )
                if runtime.current_task is not None and not runtime.current_task.done():
                    try:
                        await runtime.current_task
                    except asyncio.CancelledError:
                        logger.info("Current task cancelled during interrupt for session %s", session_id)
                    except Exception:  # noqa: BLE001
                        logger.exception("Interrupted task exited with error for session %s", session_id)
                await _log_web_message(
                    runtime,
                    session_id,
                    "user",
                    instruction,
                    title=instruction[:200],
                    metadata={"source": "websocket", "action": "interrupt", "client": client_metadata or {}},
                )
                _start_navigation_task(websocket, runtime, session_id, instruction)
            elif action == "queue":
                if not runtime.task_running:
                    await _start_idle_navigation_from_control_action(
                        websocket,
                        runtime,
                        session_id,
                        instruction,
                        action="queue",
                        task_label=task_label,
                        title_candidate=title_candidate,
                        client_metadata=client_metadata,
                    )
                    continue
                runtime.queued_instructions.append(instruction)
                await _send_step(
                    websocket,
                    {"type": "queue", "content": f"Queued instruction: {instruction}"},
                    runtime=runtime,
                    session_id=session_id,
                )
                await _log_web_message(
                    runtime,
                    session_id,
                    "user",
                    instruction,
                    title=instruction[:200],
                    metadata={"source": "websocket", "action": "queue", "client": client_metadata or {}},
                )
            elif action == "dequeue":
                raw_index = data.get("index", -1)
                try:
                    index = int(raw_index)
                except (TypeError, ValueError):
                    await websocket.send_json({"type": "error", "data": {"message": "Invalid queue index"}})
                    continue

                if 0 <= index < len(runtime.queued_instructions):
                    removed = runtime.queued_instructions.pop(index)
                    await _send_step(
                        websocket,
                        {"type": "queue", "content": f"Removed queued instruction: {removed}"},
                        runtime=runtime,
                        session_id=session_id,
                    )
                else:
                    await websocket.send_json({"type": "error", "data": {"message": "Invalid queue index"}})
            elif action == "config":
                candidate_settings = data.get("settings", {})
                if not isinstance(candidate_settings, dict):
                    await websocket.send_json({"type": "error", "data": {"message": "Invalid config payload: settings must be an object"}})
                    continue
                runtime.settings = _merge_runtime_settings(runtime.settings, candidate_settings)
                await _send_step(
                    websocket,
                    {"type": "config", "content": "Session settings updated"},
                    runtime=runtime,
                    session_id=session_id,
                )
            elif action == "audio_chunk":
                transcript = await live_manager.process_audio(session_id, data.get("audio"))
                if transcript:
                    await _send_transcript(websocket, transcript)
                    if runtime.task_running:
                        runtime.steering_context.append(transcript)
                        await _log_web_message(
                            runtime,
                            session_id,
                            "user",
                            transcript,
                            metadata={"source": "voice", "action": "steer"},
                        )
                    else:
                        await _log_web_message(
                            runtime,
                            session_id,
                            "user",
                            transcript,
                            title=transcript[:200],
                            metadata={"source": "voice", "action": "navigate"},
                        )
                        _start_navigation_task(websocket, runtime, session_id, transcript)
            elif action == "user_input_response":
                request_id = str(data.get("request_id", ""))
                response_text = str(data.get("response", ""))
                fut = runtime.pending_user_inputs.get(request_id)
                if fut and not fut.done():
                    fut.set_result(response_text)
                else:
                    logger.debug("user_input_response for unknown/expired request_id=%s", request_id)
            elif action == "ping":
                # Client keepalive ping — just ignore silently (server already handles ws-level pings)
                pass
            elif action == "spawn_subagent":
                # ── Spawn a sub-agent ──────────────────────────────────
                active_mode = _normalize_runtime_mode(runtime.settings)
                if "spawn_subagent" in blocked_tools_for_mode(active_mode):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {
                                "type": "mode_policy_refusal",
                                "requested_tool": "spawn_subagent",
                                "effective_mode": active_mode,
                                "reason": "tool_disallowed_for_mode",
                                "allowed_alternatives": allowed_tool_alternatives(active_mode),
                            },
                        }
                    )
                    continue
                sub_instruction = str(data.get("instruction", "")).strip()
                sub_model = str(data.get("model", runtime.settings.get("model", ""))).strip()
                if not sub_instruction:
                    await websocket.send_json({"type": "error", "data": {"message": "spawn_subagent: instruction is required"}})
                    continue
                if not sub_model:
                    sub_model = str(runtime.settings.get("model", "nvidia/nemotron-3-super-120b-a12b")).strip()

                async def _sub_send(msg: dict[str, Any], _ws: "WebSocket" = websocket) -> None:
                    try:
                        await _ws.send_json(msg)
                    except Exception:  # noqa: BLE001
                        pass

                sub_id = await runtime.subagent_manager.spawn(
                    instruction=sub_instruction,
                    model=sub_model,
                    parent_user_uid=runtime.user_uid,
                    orchestrator=_get_orchestrator(),
                    parent_settings=runtime.settings,
                    send_to_parent=_sub_send,
                    on_user_input=None,  # sub-agents don't forward user-input to parent for now
                )
                await websocket.send_json({
                    "type": "subagent_spawned",
                    "data": {
                        "sub_id": sub_id,
                        "instruction": sub_instruction,
                        "model": sub_model,
                    },
                })
                # Also send updated agent count
                await websocket.send_json({
                    "type": "subagent_list",
                    "data": {"agents": runtime.subagent_manager.list_agents()},
                })
            elif action == "message_subagent":
                # ── Steer a running sub-agent ──────────────────────────
                sub_id = str(data.get("sub_id", "")).strip()
                sub_message = str(data.get("message", "")).strip()
                if not sub_id or not sub_message:
                    await websocket.send_json({"type": "error", "data": {"message": "message_subagent: sub_id and message are required"}})
                    continue
                ok = await runtime.subagent_manager.send_message(sub_id, sub_message)
                if not ok:
                    await websocket.send_json({"type": "error", "data": {"message": f"Sub-agent {sub_id} not found or not running"}})
            elif action == "cancel_subagent":
                # ── Cancel a specific sub-agent ────────────────────────
                sub_id = str(data.get("sub_id", "")).strip()
                if not sub_id:
                    await websocket.send_json({"type": "error", "data": {"message": "cancel_subagent: sub_id is required"}})
                    continue
                ok = await runtime.subagent_manager.cancel(sub_id)
                await websocket.send_json({
                    "type": "subagent_cancelled",
                    "data": {"sub_id": sub_id, "found": ok},
                })
                await websocket.send_json({
                    "type": "subagent_list",
                    "data": {"agents": runtime.subagent_manager.list_agents()},
                })
            elif action == "list_subagents":
                # ── List all sub-agents for this session ───────────────
                await websocket.send_json({
                    "type": "subagent_list",
                    "data": {"agents": runtime.subagent_manager.list_agents()},
                })
            elif action == "stop":
                runtime.cancel_event.set()
                break
            else:
                await websocket.send_json({"type": "error", "data": {"message": f"Unknown action: {action}"}})
    except WebSocketDisconnect:
        logger.info("Websocket disconnected")
    finally:
        if runtime.current_task is not None and not runtime.current_task.done() and runtime.task_running:
            runtime.cancel_event.set()
            runtime.current_task.cancel()
            try:
                await runtime.current_task
            except asyncio.CancelledError:
                logger.info("Cancelled active websocket task during shutdown for session %s", session_id)
        # Cancel all sub-agents when parent disconnects
        await runtime.subagent_manager.cancel_all()
        logger.info("All sub-agents cancelled for session %s", session_id)
        if runtime.user_uid:
            _user_runtimes.pop(runtime.user_uid, None)
        await cleanup_session_workspace(session_id)
        await live_manager.close_session(session_id)


async def _log_platform_message(
    user_id: str | None,
    *,
    platform: str,
    platform_chat_id: str,
    role: str,
    content: str,
    title: str,
    metadata: dict[str, Any] | None = None,
    platform_message_id: str | None = None,
) -> None:
    """Persist a platform message to conversation storage when an owner is available."""
    if not user_id:
        return
    session_iter = get_session()
    db = await anext(session_iter)
    try:
        conversation = await get_or_create_conversation(
            db,
            user_id=user_id,
            platform=platform,
            platform_chat_id=str(platform_chat_id),
            title=title,
        )
        await append_message(
            db,
            conversation_id=conversation.id,
            role=role,
            content=content,
            metadata=metadata or {},
            platform_message_id=platform_message_id,
        )
    finally:
        await session_iter.aclose()


# ── Integration webhook / registration endpoints ─────────────────────


@app.post("/api/integrations/telegram/webhook/{integration_id}")
async def telegram_webhook(integration_id: str, request: Request) -> dict[str, Any]:
    integration = telegram_registry.get_telegram(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    config = telegram_registry.get_config(integration_id)
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if hasattr(integration, "validate_webhook_secret"):
        if not integration.validate_webhook_secret(secret):
            raise HTTPException(status_code=403, detail="Invalid secret token")
    else:
        expected_secret = str(config.get("webhook_secret", ""))
        if expected_secret and secret != expected_secret:
            raise HTTPException(status_code=403, detail="Invalid secret token")
    update = await request.json()
    result = await integration.execute_tool("telegram_webhook_update", {"update": update})
    owner_user_id = str(config.get("owner_user_id", "")).strip() or None
    callback_mode, callback_mode_valid = _parse_telegram_mode_callback(update)
    if callback_mode is not None:
        callback_message = update.get("callback_query", {}).get("message", {})
        callback_chat_id = (callback_message.get("chat") or {}).get("id")
        if not owner_user_id:
            if callback_chat_id is not None:
                await integration.execute_tool(
                    "telegram_send_message",
                    {
                        "chat_id": str(callback_chat_id),
                        "text": "⚠️ Mode switching is only available for the owner session.",
                    },
                )
            return {"ok": True}
        runtime = _user_runtimes.get(owner_user_id)
        if not runtime:
            if callback_chat_id is not None:
                await integration.execute_tool(
                    "telegram_send_message",
                    {"chat_id": str(callback_chat_id), "text": "⚠️ No active session. Start a session first."},
                )
            return {"ok": True}
        if not callback_mode_valid:
            if callback_chat_id is not None:
                allowed = ", ".join(MODE_LABELS.keys())
                await integration.execute_tool(
                    "telegram_send_message",
                    {
                        "chat_id": str(callback_chat_id),
                        "text": f"❌ Invalid mode selection. Allowed modes: {allowed}",
                    },
                )
            return {"ok": True}
        runtime.settings["agent_mode"] = callback_mode
        mode_label = MODE_LABELS.get(callback_mode, callback_mode.title())
        if callback_chat_id is not None:
            await integration.execute_tool(
                "telegram_send_message",
                {"chat_id": str(callback_chat_id), "text": f"✅ Mode switched to *{mode_label}*"},
            )
        return {"ok": True}
    chat_id, text_content, platform_message_id = _extract_telegram_message(update)

    # Slash command handling
    if chat_id and text_content and text_content.startswith("/"):
        bot_cfg = _bot_configs.get(f"telegram:{integration_id}", {})
        # Allow-from check
        allow_from = bot_cfg.get("allow_from", [])
        if allow_from:
            sender_id = str(_get_telegram_sender_id(update))
            if sender_id not in allow_from:
                return {"ok": True}  # silently ignore unauthorized senders
        ack_reaction = bot_cfg.get("ack_reaction", "")
        cmd_response = await _handle_slash_command(
            text=text_content,
            owner_uid=owner_user_id,
            platform="telegram",
            integration_id=integration_id,
            chat_id=chat_id,
            ack_reaction=ack_reaction,
        )
        if cmd_response:
            if isinstance(cmd_response, dict):
                await integration.execute_tool(
                    "telegram_send_message",
                    {
                        "chat_id": chat_id,
                        "text": str(cmd_response.get("text", "")),
                        "reply_markup": cmd_response.get("reply_markup"),
                    },
                )
            else:
                await integration.execute_tool("telegram_send_message", {"chat_id": chat_id, "text": cmd_response})
        return {"ok": True}

    if chat_id and text_content:
        await _log_platform_message(
            owner_user_id,
            platform="telegram",
            platform_chat_id=chat_id,
            role="user",
            content=text_content,
            title=text_content[:200],
            metadata={"integration_id": integration_id, "source": "webhook"},
            platform_message_id=platform_message_id,
        )
    return {"ok": True, "result": result}


@app.post("/api/integrations/telegram/register/{integration_id}")
async def register_telegram_integration(integration_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    session_owner_user_id = _extract_session_user_uid(request.cookies.get("aegis_session"))
    payload_owner_user_id = str(payload.get("owner_user_id", "")).strip() or None
    if session_owner_user_id and payload_owner_user_id and payload_owner_user_id != session_owner_user_id:
        raise HTTPException(status_code=403, detail="owner_user_id does not match authenticated session")
    owner_user_id = session_owner_user_id or payload_owner_user_id
    if not owner_user_id:
        raise HTTPException(
            status_code=400,
            detail="owner_user_id is required (authenticate via aegis_session or provide owner_user_id in payload)",
        )
    config = {
        "bot_token": str(payload.get("bot_token", "")).strip(),
        "delivery_mode": str(payload.get("delivery_mode", "polling")).strip(),
        "webhook_url": str(payload.get("webhook_url", "")).strip(),
        "webhook_secret": str(payload.get("webhook_secret", "")).strip(),
        "owner_user_id": owner_user_id,
    }
    integration = TelegramIntegration()
    connection = await integration.connect(config)
    telegram_registry.upsert(integration_id, integration, config)
    # Auto-register slash commands
    if connection.get("connected"):
        asyncio.create_task(_register_telegram_commands(integration))
    return {"ok": True, "connection": connection}


@app.post("/api/integrations/telegram/{integration_id}/test")
async def test_telegram_integration(integration_id: str) -> dict[str, Any]:
    integration = telegram_registry.get_telegram(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    result = await integration.execute_tool("telegram_list_chats", {})
    return {"ok": bool(result.get("ok")), "result": result}


@app.post("/api/integrations/telegram/{integration_id}/send_message")
async def telegram_send_message(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    integration = telegram_registry.get_telegram(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    try:
        chat_id = int(payload.get("chat_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    text = str(payload.get("text", "")).strip()
    parse_mode = str(payload.get("parse_mode", "")).strip() or None
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    normalized_text, normalized_parse_mode = normalize_for_channel(text, channel="telegram", parse_mode=parse_mode)
    tool_payload: dict[str, Any] = {"chat_id": chat_id, "text": normalized_text}
    if normalized_parse_mode:
        tool_payload["parse_mode"] = normalized_parse_mode
    result = await integration.execute_tool("telegram_send_message", tool_payload)
    config = telegram_registry.get_config(integration_id)
    if bool(result.get("ok")):
        await _log_platform_message(
            str(config.get("owner_user_id", "")).strip() or None,
            platform="telegram",
            platform_chat_id=str(chat_id),
            role="assistant",
            content=normalized_text,
            title=f"Telegram {chat_id}",
            metadata={"integration_id": integration_id, "source": "send_message", "draft": False},
        )
    return {"ok": bool(result.get("ok")), "result": result}


@app.post("/api/integrations/telegram/{integration_id}/send_draft")
async def telegram_send_draft(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    integration = telegram_registry.get_telegram(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    try:
        chat_id = int(payload.get("chat_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    text = str(payload.get("text", "")).strip()
    parse_mode = str(payload.get("parse_mode", "")).strip() or None
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    normalized_text, normalized_parse_mode = normalize_for_channel(text, channel="telegram", parse_mode=parse_mode)
    tool_payload: dict[str, Any] = {"chat_id": chat_id, "text": normalized_text, "draft": True}
    if normalized_parse_mode:
        tool_payload["parse_mode"] = normalized_parse_mode
    result = await integration.execute_tool("telegram_send_message", tool_payload)
    config = telegram_registry.get_config(integration_id)
    if bool(result.get("ok")):
        await _log_platform_message(
            str(config.get("owner_user_id", "")).strip() or None,
            platform="telegram",
            platform_chat_id=str(chat_id),
            role="assistant",
            content=normalized_text,
            title=f"Telegram {chat_id}",
            metadata={"integration_id": integration_id, "source": "send_message", "draft": True},
        )
    return {"ok": bool(result.get("ok")), "result": result}


@app.post("/api/integrations/slack/register/{integration_id}")
async def register_slack_integration(integration_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    config = {
        "bot_token": str(payload.get("bot_token", "")).strip(),
        "oauth_token": str(payload.get("oauth_token", "")).strip(),
        "workspace": str(payload.get("workspace", "")).strip(),
        "owner_user_id": _extract_session_user_uid(request.cookies.get("aegis_session")),
    }
    integration = SlackIntegration()
    connection = await integration.connect(config)
    slack_registry.upsert(integration_id, integration, config)
    return {"ok": True, "connection": connection}


@app.post("/api/integrations/slack/webhook/{integration_id}")
async def slack_webhook(integration_id: str, request: Request) -> dict[str, Any]:
    """Handle Slack events/interactions and route shared slash commands."""
    integration = slack_registry.get_slack(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    payload = await request.json()
    result = await integration.execute_tool("slack_handle_event", {"payload": payload, "headers": dict(request.headers)})
    owner_user_id = str(slack_registry.get_config(integration_id).get("owner_user_id", "")).strip() or None

    selected_mode_raw = SlackIntegration.extract_mode_selection(payload if isinstance(payload, dict) else {})
    if selected_mode_raw:
        channel = str(payload.get("channel", {}).get("id") or payload.get("channel_id") or "").strip()
        if not owner_user_id:
            if channel:
                await integration.execute_tool(
                    "slack_send_message",
                    {"channel": channel, "text": "⚠️ Mode switching is only available for the owner session."},
                )
            return {"ok": True}
        runtime = _user_runtimes.get(owner_user_id)
        if not runtime:
            if channel:
                await integration.execute_tool("slack_send_message", {"channel": channel, "text": "⚠️ No active session. Start a session first."})
            return {"ok": True}
        selected_mode, mode_valid, mode_error = _apply_runtime_mode_update(runtime, selected_mode_raw)
        if not mode_valid:
            if channel:
                await integration.execute_tool("slack_send_message", {"channel": channel, "text": f"❌ {mode_error}"})
            return {"ok": True}
        if channel:
            await integration.execute_tool(
                "slack_send_message",
                {"channel": channel, "text": f"✅ Mode switched to *{MODE_LABELS.get(selected_mode, selected_mode.title())}*"},
            )
        return {"ok": True}

    channel, text_content, platform_message_id = _extract_slack_message(payload if isinstance(payload, dict) else {})
    if channel and text_content and text_content.startswith("/"):
        cmd_response = await _handle_slash_command(
            text=text_content,
            owner_uid=owner_user_id,
            platform="slack",
            integration_id=integration_id,
            chat_id=channel,
        )
        if isinstance(cmd_response, dict):
            await integration.execute_tool(
                "slack_send_message",
                {"channel": channel, "text": str(cmd_response.get("text", "")), "blocks": cmd_response.get("blocks")},
            )
        elif cmd_response:
            await integration.execute_tool("slack_send_message", {"channel": channel, "text": cmd_response})
        return {"ok": True}

    if channel and text_content:
        await _log_platform_message(
            owner_user_id,
            platform="slack",
            platform_chat_id=channel,
            role="user",
            content=text_content,
            title=text_content[:200],
            metadata={"integration_id": integration_id, "source": "webhook"},
            platform_message_id=platform_message_id,
        )
    return {"ok": True, "result": result}


@app.post("/api/integrations/slack/{integration_id}/test")
async def test_slack_integration(integration_id: str) -> dict[str, Any]:
    integration = slack_registry.get_slack(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    result = await integration.execute_tool("slack_list_channels", {})
    return {"ok": bool(result.get("ok")), "result": result}


@app.post("/api/integrations/slack/{integration_id}/send_message")
async def slack_send_message(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    integration = slack_registry.get_slack(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    channel = str(payload.get("channel", "")).strip()
    text = str(payload.get("text", "")).strip()
    if not channel:
        raise HTTPException(status_code=400, detail="Channel is required")
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    normalized_text, _ = normalize_for_channel(text, channel="slack")
    result = await integration.execute_tool("slack_send_message", {"channel": channel, "text": normalized_text})
    config = slack_registry.get_config(integration_id)
    if bool(result.get("ok")):
        await _log_platform_message(
            str(config.get("owner_user_id", "")).strip() or None,
            platform="slack",
            platform_chat_id=channel,
            role="assistant",
            content=normalized_text,
            title=f"Slack {channel}",
            metadata={"integration_id": integration_id, "source": "send_message"},
        )
    return {"ok": bool(result.get("ok")), "result": result}


@app.post("/api/integrations/discord/register/{integration_id}")
async def register_discord_integration(integration_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    config = {
        "bot_token": str(payload.get("bot_token", "")).strip(),
        "guild_id": str(payload.get("guild_id", "")).strip(),
        "owner_user_id": _extract_session_user_uid(request.cookies.get("aegis_session")),
    }
    integration = DiscordIntegration()
    connection = await integration.connect(config)
    discord_registry.upsert(integration_id, integration, config)
    return {"ok": True, "connection": connection}


@app.post("/api/integrations/discord/webhook/{integration_id}")
async def discord_webhook(integration_id: str, request: Request) -> dict[str, Any]:
    """Handle Discord interactions/events and route shared slash commands."""
    integration = discord_registry.get_discord(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    payload = await request.json()
    result = await integration.execute_tool("discord_handle_event", {"payload": payload, "headers": dict(request.headers)})
    owner_user_id = str(discord_registry.get_config(integration_id).get("owner_user_id", "")).strip() or None

    selected_mode_raw = DiscordIntegration.extract_mode_selection(payload if isinstance(payload, dict) else {})
    if selected_mode_raw:
        channel = str(payload.get("channel_id") or "").strip()
        if not owner_user_id:
            if channel:
                await integration.execute_tool(
                    "discord_send_message",
                    {"channel": channel, "text": "⚠️ Mode switching is only available for the owner session."},
                )
            return {"ok": True}
        runtime = _user_runtimes.get(owner_user_id)
        if not runtime:
            if channel:
                await integration.execute_tool("discord_send_message", {"channel": channel, "text": "⚠️ No active session. Start a session first."})
            return {"ok": True}
        selected_mode, mode_valid, mode_error = _apply_runtime_mode_update(runtime, selected_mode_raw)
        if not mode_valid:
            if channel:
                await integration.execute_tool("discord_send_message", {"channel": channel, "text": f"❌ {mode_error}"})
            return {"ok": True}
        if channel:
            await integration.execute_tool(
                "discord_send_message",
                {"channel": channel, "text": f"✅ Mode switched to *{MODE_LABELS.get(selected_mode, selected_mode.title())}*"},
            )
        return {"ok": True}

    channel, text_content, platform_message_id = _extract_discord_message(payload if isinstance(payload, dict) else {})
    if channel and text_content and text_content.startswith("/"):
        cmd_response = await _handle_slash_command(
            text=text_content,
            owner_uid=owner_user_id,
            platform="discord",
            integration_id=integration_id,
            chat_id=channel,
        )
        if isinstance(cmd_response, dict):
            await integration.execute_tool(
                "discord_send_message",
                {"channel": channel, "text": str(cmd_response.get("text", "")), "components": cmd_response.get("components")},
            )
        elif cmd_response:
            await integration.execute_tool("discord_send_message", {"channel": channel, "text": cmd_response})
        return {"ok": True}

    if channel and text_content:
        await _log_platform_message(
            owner_user_id,
            platform="discord",
            platform_chat_id=channel,
            role="user",
            content=text_content,
            title=text_content[:200],
            metadata={"integration_id": integration_id, "source": "webhook"},
            platform_message_id=platform_message_id,
        )
    return {"ok": True, "result": result}


@app.post("/api/integrations/discord/{integration_id}/test")
async def test_discord_integration(integration_id: str) -> dict[str, Any]:
    integration = discord_registry.get_discord(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    result = await integration.execute_tool("discord_list_channels", {})
    return {"ok": bool(result.get("ok")), "result": result}


@app.post("/api/integrations/discord/{integration_id}/send_message")
async def discord_send_message(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    integration = discord_registry.get_discord(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    channel = str(payload.get("channel", "")).strip()
    text = str(payload.get("text", "")).strip()
    if not channel:
        raise HTTPException(status_code=400, detail="Channel is required")
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    normalized_text, _ = normalize_for_channel(text, channel="discord")
    result = await integration.execute_tool("discord_send_message", {"channel": channel, "text": normalized_text})
    config = discord_registry.get_config(integration_id)
    if bool(result.get("ok")):
        await _log_platform_message(
            str(config.get("owner_user_id", "")).strip() or None,
            platform="discord",
            platform_chat_id=channel,
            role="assistant",
            content=normalized_text,
            title=f"Discord {channel}",
            metadata={"integration_id": integration_id, "source": "send_message"},
        )
    return {"ok": bool(result.get("ok")), "result": result}


@app.post("/api/integrations/github/register/{integration_id}")
@app.post("/api/integrations/github-pat/register/{integration_id}")
async def register_github_integration(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    repo_permissions = payload.get("repo_permissions", {}) or {}
    if not isinstance(repo_permissions, dict):
        repo_permissions = {}
    config = {
        "token": str(payload.get("token", "")).strip(),
        "webhook_secret": str(payload.get("webhook_secret", "")).strip(),
        "app_id": str(payload.get("app_id", "")).strip(),
        "repo_permissions": repo_permissions,
    }
    integration = GitHubIntegration()
    connection = await integration.connect(config)
    github_registry.upsert(integration_id, integration, config)
    return {"connection": connection, "tools": integration.list_tools()}


@app.post("/api/integrations/github/{integration_id}/test")
@app.post("/api/integrations/github-pat/{integration_id}/test")
async def test_github_integration(integration_id: str) -> dict[str, Any]:
    integration = github_registry.get_github(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="GitHub integration not found")
    return await integration.execute_tool("github_list_repos", {"per_page": 5})


@app.post("/api/integrations/github/{integration_id}/webhook")
@app.post("/api/integrations/github-pat/{integration_id}/webhook")
async def github_webhook(integration_id: str, request: Request) -> dict[str, Any]:
    """Receive GitHub webhook events (push, PR, issue, etc.)."""
    integration = github_registry.get_github(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="GitHub integration not found")

    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    config = github_registry.get_config(integration_id)
    webhook_secret = str(config.get("webhook_secret", "")).strip()
    if webhook_secret and not integration.verify_webhook_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    import json as _json

    try:
        payload = _json.loads(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    event_type = request.headers.get("X-GitHub-Event", "ping")
    return {"ok": True, "event": event_type, "action": payload.get("action"), "received": True}


# ── Cloud Agent Spawn endpoints ───────────────────────────────────────


@app.post("/api/agents/spawn")
async def spawn_agent_task(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_verify_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Spawn a new cloud agent task."""
    instruction = str(payload.get("instruction", "")).strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction is required")

    task = await create_agent_task(
        db,
        user_id=user["uid"],
        instruction=instruction,
        platform=str(payload.get("platform", "web")).strip(),
        platform_chat_id=payload.get("platform_chat_id"),
        platform_message_id=payload.get("platform_message_id"),
        agent_type=str(payload.get("agent_type", "navigator")).strip(),
        provider=payload.get("provider"),
        model=payload.get("model"),
    )
    return {
        "task_id": task.id,
        "status": task.status,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


@app.get("/api/agents/tasks")
async def list_agent_tasks(
    status: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: dict[str, Any] = Depends(_verify_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List agent tasks for the current user."""
    tasks = await get_user_tasks(db, user["uid"], status=status, platform=platform, limit=limit, offset=offset)
    return {
        "tasks": [
            {
                "id": t.id,
                "instruction": t.instruction[:200],
                "status": t.status,
                "platform": t.platform,
                "agent_type": t.agent_type,
                "provider": t.provider,
                "model": t.model,
                "credits_used": t.credits_used,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ]
    }


@app.get("/api/agents/tasks/{task_id}")
async def get_agent_task(
    task_id: str,
    user: dict[str, Any] = Depends(_verify_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a specific agent task with actions."""
    task = await get_task_by_id(db, task_id)
    if not task or task.user_id != user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found")

    actions = await get_task_actions(db, task_id)
    return {
        "id": task.id,
        "instruction": task.instruction,
        "status": task.status,
        "platform": task.platform,
        "agent_type": task.agent_type,
        "provider": task.provider,
        "model": task.model,
        "sandbox_id": task.sandbox_id,
        "result_summary": task.result_summary,
        "error_message": task.error_message,
        "credits_used": task.credits_used,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "actions": [
            {
                "id": a.id,
                "sequence": a.sequence,
                "action_type": a.action_type,
                "description": a.description,
                "duration_ms": a.duration_ms,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in actions
        ],
    }


@app.post("/api/agents/tasks/{task_id}/cancel")
async def cancel_agent_task(
    task_id: str,
    user: dict[str, Any] = Depends(_verify_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Cancel a running or pending agent task."""
    task = await get_task_by_id(db, task_id)
    if not task or task.user_id != user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel task in '{task.status}' status")

    updated = await update_task_status(db, task_id, "cancelled")
    return {"task_id": task_id, "status": updated.status if updated else "cancelled"}


# ── Bot slash command infrastructure ────────────────────────────────


TELEGRAM_SLASH_COMMANDS = [
    {"command": "run", "description": "Start a task: /run <instruction>"},
    {"command": "steer", "description": "Steer mid-task: /steer <guidance>"},
    {"command": "interrupt", "description": "Stop the current task"},
    {"command": "queue", "description": "Queue a task: /queue <instruction>"},
    {"command": "status", "description": "Show agent status and credits"},
    {"command": "model", "description": "Show current model"},
    {"command": "mode", "description": "Show or switch agent mode"},
    {"command": "models", "description": "List models and switch"},
    {"command": "stream", "description": "Live browser screenshots: /stream start|stop"},
    {"command": "help", "description": "Show all commands"},
]


async def _register_telegram_commands(integration: TelegramIntegration) -> None:
    try:
        await integration.set_my_commands(TELEGRAM_SLASH_COMMANDS)
        logger.info("Telegram slash commands registered")
    except Exception as exc:
        logger.warning("Failed to register Telegram commands: %s", exc)


async def _on_frame_for_stream(user_uid: str, image_b64: str) -> None:
    """Forward a frame to stream subscribers (used when task is triggered from bot)."""
    sub = _stream_subscribers.get(user_uid)
    if not sub:
        return
    now = _time.monotonic()
    if now - sub.get("last_sent_at", 0) < 3.0:
        return
    sub["last_sent_at"] = now
    platform = sub.get("platform")
    integration_id = sub.get("integration_id")
    chat_id = sub.get("chat_id")
    if platform == "telegram":
        integration = telegram_registry.get_telegram(integration_id)
        if integration:
            await integration.send_photo(chat_id, image_b64)
    elif platform == "discord":
        integration = discord_registry.get_discord(integration_id)
        if integration:
            await integration.send_image(sub.get("channel_id", chat_id), image_b64)


async def _run_navigation_task_from_bot(
    runtime: "SessionRuntime",
    owner_uid: str,
    platform: str,
    integration_id: str,
    chat_id: Any,
    instruction: str,
) -> None:
    """Run a navigation task triggered from a bot command (no websocket)."""
    runtime.task_running = True
    runtime.cancel_event.clear()
    steps: list[Any] = []
    try:
        result = await _get_orchestrator().execute_task(
            session_id=f"bot_{owner_uid}",
            instruction=instruction,
            on_step=lambda step: steps.append(step),
            on_frame=lambda img: _on_frame_for_stream(owner_uid, img),
            cancel_event=runtime.cancel_event,
            steering_context=runtime.steering_context,
            settings=runtime.settings,
            on_workflow_step=lambda _: None,
            user_uid=owner_uid,
        )
        status = result.get("status", "completed")
        reply = f"✅ Task {status}: {instruction[:60]}"
    except asyncio.CancelledError:
        reply = "🛑 Task was interrupted."
    except Exception as exc:
        reply = f"❌ Task failed: {exc}"
    finally:
        runtime.task_running = False
        await cleanup_session_workspace(f"bot_{owner_uid}")
    # Send result back to bot
    if platform == "telegram":
        integration = telegram_registry.get_telegram(integration_id)
        if integration:
            normalized_reply, _ = normalize_for_channel(reply, channel="telegram")
            await integration.execute_tool("telegram_send_message", {"chat_id": chat_id, "text": normalized_reply})
    elif platform == "discord":
        integration = discord_registry.get_discord(integration_id)
        if integration:
            normalized_reply, _ = normalize_for_channel(reply, channel="discord")
            await integration.execute_tool("discord_send_message", {"channel": str(chat_id), "text": normalized_reply})


def _get_telegram_sender_id(update: dict[str, Any]) -> str:
    callback_query = update.get("callback_query") or {}
    callback_from = callback_query.get("from") or {}
    if callback_from.get("id") is not None:
        return str(callback_from.get("id"))
    msg = update.get("message") or update.get("edited_message") or {}
    return str((msg.get("from") or {}).get("id", ""))


def _extract_telegram_message(update: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Extract chat/text/message-id from message or callback payloads."""
    callback_query = update.get("callback_query") or {}
    if callback_query:
        message = callback_query.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        text = str(callback_query.get("data", "")).strip() or None
        message_id = message.get("message_id")
        return (
            str(chat_id) if chat_id is not None else None,
            text,
            str(message_id) if message_id is not None else None,
        )

    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = str(message.get("text", "")).strip() or None
    message_id = message.get("message_id")
    return (
        str(chat_id) if chat_id is not None else None,
        text,
        str(message_id) if message_id is not None else None,
    )


def _extract_slack_message(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Extract channel/text/message-id from a Slack event payload."""
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    channel = event.get("channel") or payload.get("channel_id")
    text = event.get("text") or payload.get("text")
    message_id = event.get("ts") or payload.get("message_ts")
    return (
        str(channel) if channel is not None and str(channel).strip() else None,
        str(text).strip() if text is not None and str(text).strip() else None,
        str(message_id) if message_id is not None and str(message_id).strip() else None,
    )


def _extract_discord_message(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Extract channel/text/message-id from Discord interaction/event payload."""
    channel = payload.get("channel_id")
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    options = data.get("options") if isinstance(data.get("options"), list) else []
    option_value = ""
    if options and isinstance(options[0], dict):
        option_value = str(options[0].get("value") or "").strip()
    text = option_value or str(data.get("text") or "").strip() or str(payload.get("content") or "").strip()
    message_id = message.get("id") or payload.get("id")
    return (
        str(channel) if channel is not None and str(channel).strip() else None,
        text or None,
        str(message_id) if message_id is not None and str(message_id).strip() else None,
    )


async def _handle_slash_command(
    text: str,
    owner_uid: str | None,
    platform: str,
    integration_id: str,
    chat_id: Any,
    ack_reaction: str = "",
) -> str | dict[str, Any] | None:
    """Parse a slash command and execute the appropriate action. Returns a reply string or None."""
    parts = text.strip().split(None, 1)
    cmd = parts[0].lstrip("/").lower().split("@")[0]  # strip bot username suffix
    arg = parts[1].strip() if len(parts) > 1 else ""

    runtime = _user_runtimes.get(owner_uid) if owner_uid else None

    if cmd == "help":
        return (
            "🤖 *Aegis Bot Commands*\n\n"
            "/run <instruction> — start a task\n"
            "/steer <guidance> — nudge mid-task\n"
            "/interrupt — stop current task\n"
            "/queue <instruction> — queue for later\n"
            "/status — agent status + credits\n"
            "/model — current model\n"
            "/mode [name] — show or switch mode\n"
            "/models — list & switch model\n"
            "/stream start|stop — live screenshots\n"
            "/reason on|off|low|medium|high|stream|status — reasoning mode\n"
            "/help — this message"
        )

    if cmd == "status":
        if not runtime:
            return "⚪ Agent offline — open the Aegis app to start a session."
        state = "🟢 Working" if runtime.task_running else "🟡 Idle"
        queued = len(runtime.queued_instructions)
        model = runtime.settings.get("model", "default")
        provider = runtime.settings.get("provider", "")
        credits_info = ""
        try:
            from backend.database import get_session as _get_db_session
            async for db in _get_db_session():
                bal = await get_or_create_balance(db, owner_uid)
                credits_info = f"\n💳 Credits: {bal.balance:.4f}"
                break
        except Exception:
            pass
        mode = normalize_agent_mode(runtime.settings.get("agent_mode", ""))
        mode_label = MODE_LABELS.get(mode, mode.title())
        return f"{state}\n🧠 Model: {model} ({provider})\n🧭 Mode: {mode_label}\n📋 Queued: {queued}{credits_info}"

    if cmd == "model":
        if not runtime:
            return "⚪ No active session."
        model = runtime.settings.get("model", "not set")
        provider = runtime.settings.get("provider", "")
        return f"🧠 Current model: *{model}* ({provider})"

    if cmd == "mode":
        if not runtime:
            return "⚪ No active session."
        if not arg:
            active_mode = normalize_agent_mode(runtime.settings.get("agent_mode", ""))
            return f"🧭 Current mode: *{MODE_LABELS.get(active_mode, active_mode.title())}*"
        requested_mode = normalize_agent_mode(arg.replace("-", "_").replace(" ", "_"))
        runtime.settings["agent_mode"] = requested_mode
        return f"✅ Mode switched to *{MODE_LABELS.get(requested_mode, requested_mode.title())}*"

    if cmd == "models":
        providers = list_providers()
        lines = ["🧠 *Available models:*\n"]
        for p in providers[:5]:  # cap at 5 providers to avoid wall of text
            lines.append(f"*{p['displayName']}*")
            for m in p.get("models", [])[:3]:
                lines.append(f"  • {m['label']} — /setmodel {p['id']} {m['id']}")
        lines.append("\nUse /setmodel <provider> <model_id> to switch")
        return "\n".join(lines)

    if cmd == "setmodel":
        parts2 = arg.split(None, 1)
        if len(parts2) < 2:
            return "Usage: /setmodel <provider> <model_id>"
        provider_id, model_id = parts2[0], parts2[1]
        if runtime:
            runtime.settings["provider"] = provider_id
            runtime.settings["model"] = model_id
            return f"✅ Model switched to *{model_id}* ({provider_id})"
        return "⚪ No active session to update."

    if cmd == "run":
        if not arg:
            return "Usage: /run <instruction>"
        if not runtime:
            return "⚪ No active session. Open the Aegis app first."
        if runtime.task_running:
            runtime.queued_instructions.append(arg)
            return f"📋 Task queued (agent is busy): {arg[:80]}"
        asyncio.create_task(_run_navigation_task_from_bot(runtime, owner_uid, platform, integration_id, chat_id, arg))
        return f"🚀 Starting task: {arg[:80]}"

    if cmd == "steer":
        if not arg:
            return "Usage: /steer <guidance>"
        if not runtime:
            return "⚪ No active session."
        runtime.steering_context.append(arg)
        return f"🎯 Steering note added: {arg[:80]}"

    if cmd == "interrupt":
        if not runtime or not runtime.task_running:
            return "⚪ No task is currently running."
        runtime.cancel_event.set()
        return "🛑 Interrupt signal sent."

    if cmd == "queue":
        if not arg:
            return "Usage: /queue <instruction>"
        if not runtime:
            return "⚪ No active session."
        runtime.queued_instructions.append(arg)
        return f"📋 Queued: {arg[:80]}"

    if cmd == "stream":
        sub_cmd = arg.lower()
        if sub_cmd == "start":
            if not runtime:
                return "⚪ No active session. Open the Aegis app first."
            _stream_subscribers[owner_uid] = {
                "platform": platform,
                "integration_id": integration_id,
                "chat_id": chat_id,
                "last_sent_at": 0,
            }
            return "📸 Screenshot stream started! You'll receive browser frames every ~3s while the agent works."
        elif sub_cmd == "stop":
            _stream_subscribers.pop(owner_uid, None)
            return "⏹ Screenshot stream stopped."
        else:
            return "Usage: /stream start|stop"

    if cmd == "reason":
        sub = arg.lower().strip()
        if not runtime:
            return "⚪ No active session."
        if sub in ("on", "true", "1"):
            runtime.settings["enable_reasoning"] = True
            return "🧠 Reasoning enabled (effort: medium). Agent will think before each step."
        elif sub in ("off", "false", "0"):
            runtime.settings["enable_reasoning"] = False
            return "⭕ Reasoning disabled."
        elif sub in ("low", "medium", "high"):
            runtime.settings["enable_reasoning"] = True
            runtime.settings["reasoning_effort"] = sub
            return f"🧠 Reasoning enabled with effort: *{sub}*."
        elif sub == "stream":
            runtime.settings["enable_reasoning"] = True
            runtime.settings["stream_reasoning"] = True
            return "🧠 Reasoning enabled with live streaming. You'll receive thinking updates in real-time."
        elif sub == "status":
            enabled = runtime.settings.get("enable_reasoning", False)
            effort = runtime.settings.get("reasoning_effort", "medium")
            streaming = runtime.settings.get("stream_reasoning", False)
            status = "enabled" if enabled else "disabled"
            return f"🧠 Reasoning: *{status}* | effort: {effort} | stream: {'on' if streaming else 'off'}"
        else:
            return (
                "Usage: /reason <on|off|low|medium|high|stream|status>\n"
                "  on/off — enable or disable reasoning\n"
                "  low/medium/high — set effort level\n"
                "  stream — enable with live streaming to this chat\n"
                "  status — show current settings"
            )

    return f"❓ Unknown command: /{cmd}\nType /help for a list of commands."


def _telegram_mode_reply_markup() -> dict[str, Any]:
    """Build Telegram inline keyboard for all available modes."""
    return TelegramIntegration.mode_selector_reply_markup(MODE_LABELS)


def _parse_telegram_mode_callback(update: dict[str, Any]) -> tuple[str | None, bool]:
    """Parse Telegram callback payload for mode selection actions."""
    callback = update.get("callback_query") or {}
    mode_data = TelegramIntegration.extract_mode_selection(callback_data=callback.get("data"))
    if mode_data is None:
        return None, False
    resolved_mode, is_valid = validate_requested_mode(mode_data)
    return resolved_mode, is_valid


# ── Bot config endpoints ─────────────────────────────────────────────


@app.get("/api/integrations/{platform}/config/{integration_id}")
async def get_bot_config(platform: str, integration_id: str, request: Request) -> dict[str, Any]:
    _get_current_user(request)  # auth check
    cfg = _bot_configs.get(f"{platform}:{integration_id}", {})
    return {"ok": True, "config": cfg}


@app.post("/api/integrations/{platform}/config/{integration_id}")
async def save_bot_config(platform: str, integration_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    _get_current_user(request)
    key = f"{platform}:{integration_id}"
    _bot_configs[key] = payload
    # Auto-register Telegram slash commands if token available
    if platform == "telegram":
        integration = telegram_registry.get_telegram(integration_id)
        if integration and payload.get("slash_commands_enabled", True):
            asyncio.create_task(_register_telegram_commands(integration))
    return {"ok": True}


# ── Frontend static files ────────────────────────────────────────────

if FRONTEND_DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_DIR / "assets"), name="assets")

    FRONTEND_SPA_ROUTES = {"", "app", "automations", "settings", "admin"}
    FRONTEND_SPA_PREFIX_ROUTES = ("app/", "automations/", "settings/", "admin/", "use-case/", "docs/")
    FRONTEND_STATIC_PAGES = {
        "about": "about.html",
        "services": "services.html",
        "blog": "blog.html",
        "contact": "contact.html",
        "docs": "docs.html",
        "auth": "auth.html",
        "privacy": "privacy.html",
        "terms": "terms.html",
        "portfolio": "portfolio.html",
        "pricing": "pricing.html",
    }

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str) -> FileResponse:
        """Serve compiled frontend files in production with explicit 404 handling."""
        normalized = full_path.strip("/")
        first_segment = normalized.split("/", 1)[0] if normalized else ""

        static_page = FRONTEND_STATIC_PAGES.get(first_segment)
        if normalized == first_segment and static_page:
            static_candidate = FRONTEND_DIST_DIR / static_page
            if static_candidate.exists():
                return FileResponse(static_candidate)

        candidate = (FRONTEND_DIST_DIR / normalized).resolve()
        try:
            candidate.relative_to(FRONTEND_DIST_DIR.resolve())
        except ValueError:
            return FileResponse(FRONTEND_DIST_DIR / "404.html", status_code=404)

        if normalized and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)

        if normalized in FRONTEND_SPA_ROUTES or any(normalized.startswith(prefix) for prefix in FRONTEND_SPA_PREFIX_ROUTES):
            return FileResponse(FRONTEND_DIST_DIR / "index.html")

        return FileResponse(FRONTEND_DIST_DIR / "404.html", status_code=404)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
