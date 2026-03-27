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
from backend.connectors.router import connector_router
from backend.gallery.router import gallery_router
from backend.payments import payments_router
from backend.planner.executor_routes import executor_router
from backend.planner.router import planner_router
from backend.conversation_service import append_message, get_or_create_conversation, update_conversation_title
from backend.database import get_session, init_db, create_tables, SupportThread, SupportMessage, UserConnection
from backend.credit_rates import CREDIT_RATES, get_tier
from backend.credit_service import check_credits, get_or_create_balance, get_usage_history, get_usage_summary
from backend.key_management import KeyManager
from backend.providers import get_provider, list_providers
from config import settings
from integrations.discord import DiscordIntegration
from integrations.github_connector import GitHubIntegration
from integrations.slack_connector import SlackIntegration
from integrations.telegram import TelegramIntegration
from orchestrator import AgentOrchestrator
from session import LiveSessionManager

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
app.include_router(automation_router)
app.include_router(connector_router)
app.include_router(gallery_router)
app.include_router(payments_router)
app.include_router(planner_router)
app.include_router(executor_router)

orchestrator: AgentOrchestrator | None = None
live_manager = LiveSessionManager()
key_manager = KeyManager(settings.ENCRYPTION_SECRET)
db_init_task: asyncio.Task[None] | None = None
db_init_error: str | None = None
db_ready = False

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
        self._integrations: dict[str, dict[str, GitHubIntegration]] = {}
        self._configs: dict[str, dict[str, dict[str, Any]]] = {}

    def get_github(self, owner_user_id: str, integration_id: str) -> GitHubIntegration | None:
        return self._integrations.get(owner_user_id, {}).get(integration_id)

    def get_config(self, owner_user_id: str, integration_id: str) -> dict[str, Any]:
        return self._configs.get(owner_user_id, {}).get(integration_id, {})

    def list_candidates(self, integration_id: str) -> list[tuple[str, GitHubIntegration, dict[str, Any]]]:
        candidates: list[tuple[str, GitHubIntegration, dict[str, Any]]] = []
        for owner_user_id, owner_integrations in self._integrations.items():
            integration = owner_integrations.get(integration_id)
            if not integration:
                continue
            config = self._configs.get(owner_user_id, {}).get(integration_id, {})
            candidates.append((owner_user_id, integration, config))
        return candidates

    def upsert(
        self,
        owner_user_id: str,
        integration_id: str,
        integration: GitHubIntegration,
        config: dict[str, Any],
    ) -> None:
        owner_integrations = self._integrations.setdefault(owner_user_id, {})
        owner_configs = self._configs.setdefault(owner_user_id, {})
        owner_integrations[integration_id] = integration
        owner_configs[integration_id] = config


slack_registry = SlackRegistry()
discord_registry = DiscordRegistry()
github_registry = GitHubRegistry()

# Maps authenticated user_uid -> active SessionRuntime (for bot command bridging)
_user_runtimes: dict[str, "SessionRuntime"] = {}

# Stream subscribers: user_uid -> {platform, integration_id, chat_id, last_sent_at}
_stream_subscribers: dict[str, dict[str, Any]] = {}

# Bot config: integration_id -> config dict
_bot_configs: dict[str, dict[str, Any]] = {}


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


# ── Provider & BYOK API routes ────────────────────────────────────────


@app.get("/api/providers")
async def get_providers() -> dict[str, Any]:
    """List all supported LLM providers and their models."""
    return {"ok": True, "providers": list_providers()}


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


# ── WebSocket helpers ─────────────────────────────────────────────────


async def _send_step(websocket: WebSocket, step: dict[str, Any]) -> None:
    """Send step payload to frontend."""
    await websocket.send_json({"type": "step", "data": step})


async def _send_frame(websocket: WebSocket, image_b64: str) -> None:
    """Send a base64 PNG frame over websocket."""
    await websocket.send_json({"type": "frame", "data": {"image": image_b64}})


async def _send_initial_frame(websocket: WebSocket) -> None:
    """Capture and send an initial frame when the websocket connects."""
    try:
        screenshot_bytes = await _get_orchestrator().executor.screenshot()
        await _send_frame(websocket, base64.b64encode(screenshot_bytes).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Initial frame capture failed: %s", exc)


async def _send_workflow_step(websocket: WebSocket, workflow_step: dict[str, Any]) -> None:
    """Send workflow graph step payload to frontend."""
    await websocket.send_json({"type": "workflow_step", "data": workflow_step})


async def _send_transcript(websocket: WebSocket, text: str, source: str = "voice") -> None:
    """Send a transcript payload to the frontend."""
    await websocket.send_json({"type": "transcript", "data": {"text": text, "source": source}})


async def _send_context_update(websocket: WebSocket, tokens_used: int, context_limit: int, compacting: bool = False) -> None:
    """Push a context-window usage update to the frontend meter."""
    await websocket.send_json({
        "type": "context_update",
        "tokens_used": tokens_used,
        "context_limit": context_limit,
        "compacting": compacting,
    })


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
    callback: Callable[[dict[str, Any]], Awaitable[None]] = lambda step: _send_step(websocket, step)
    runtime.task_running = True
    runtime.cancel_event.clear()

    try:
        result = await _get_orchestrator().execute_task(
            session_id=session_id,
            instruction=instruction,
            on_step=callback,
            on_frame=lambda image_b64: _on_frame_combined(websocket, image_b64, runtime.user_uid),
            cancel_event=runtime.cancel_event,
            steering_context=runtime.steering_context,
            settings=runtime.settings,
            on_workflow_step=lambda step: _send_workflow_step(websocket, step),
        )
        await _log_web_message(
            runtime,
            session_id,
            "assistant",
            f"Task completed: {instruction}",
            metadata={
                "source": "websocket",
                "action": "result",
                "status": result.get("status") if isinstance(result, dict) else "completed",
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
                    metadata={"source": "websocket", "action": "navigate"},
                )
                _start_navigation_task(websocket, runtime, session_id, instruction)
            elif action == "steer":
                runtime.steering_context.append(instruction)
                await _send_step(websocket, {"type": "steer", "content": f"Steering note added: {instruction}"})
                await _log_web_message(
                    runtime,
                    session_id,
                    "user",
                    instruction,
                    metadata={"source": "websocket", "action": "steer"},
                )
            elif action == "interrupt":
                runtime.cancel_event.set()
                await _send_step(websocket, {"type": "interrupt", "content": "Task interrupted"})
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
                    metadata={"source": "websocket", "action": "interrupt"},
                )
                _start_navigation_task(websocket, runtime, session_id, instruction)
            elif action == "queue":
                runtime.queued_instructions.append(instruction)
                await _send_step(websocket, {"type": "queue", "content": f"Queued instruction: {instruction}"})
            elif action == "dequeue":
                raw_index = data.get("index", -1)
                try:
                    index = int(raw_index)
                except (TypeError, ValueError):
                    await websocket.send_json({"type": "error", "data": {"message": "Invalid queue index"}})
                    continue

                if 0 <= index < len(runtime.queued_instructions):
                    removed = runtime.queued_instructions.pop(index)
                    await _send_step(websocket, {"type": "queue", "content": f"Removed queued instruction: {removed}"})
                else:
                    await websocket.send_json({"type": "error", "data": {"message": "Invalid queue index"}})
            elif action == "config":
                candidate_settings = data.get("settings", {})
                if not isinstance(candidate_settings, dict):
                    await websocket.send_json({"type": "error", "data": {"message": "Invalid config payload: settings must be an object"}})
                    continue
                runtime.settings = candidate_settings
                await _send_step(websocket, {"type": "config", "content": "Session settings updated"})
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
            elif action == "ping":
                # Client keepalive ping — just ignore silently (server already handles ws-level pings)
                pass
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
        if runtime.user_uid:
            _user_runtimes.pop(runtime.user_uid, None)
        await live_manager.close_session(session_id)


# ── Integration webhook / registration endpoints ─────────────────────


@app.post("/api/integrations/telegram/webhook/{integration_id}")
async def telegram_webhook(integration_id: str, request: Request) -> dict[str, Any]:
    integration = telegram_registry.get_telegram(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    config = telegram_registry.get_config(integration_id)
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    expected_secret = str(config.get("webhook_secret", ""))
    if expected_secret and secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")
    update = await request.json()
    result = await integration.execute_tool("telegram_webhook_update", {"update": update})
    owner_user_id = str(config.get("owner_user_id", "")).strip() or None
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
    config = {
        "bot_token": str(payload.get("bot_token", "")).strip(),
        "delivery_mode": str(payload.get("delivery_mode", "polling")).strip(),
        "webhook_url": str(payload.get("webhook_url", "")).strip(),
        "webhook_secret": str(payload.get("webhook_secret", "")).strip(),
        "owner_user_id": _extract_session_user_uid(request.cookies.get("aegis_session")),
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
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    result = await integration.execute_tool("telegram_send_message", {"chat_id": chat_id, "text": text})
    config = telegram_registry.get_config(integration_id)
    if bool(result.get("ok")):
        await _log_platform_message(
            str(config.get("owner_user_id", "")).strip() or None,
            platform="telegram",
            platform_chat_id=str(chat_id),
            role="assistant",
            content=text,
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
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    result = await integration.execute_tool("telegram_send_message", {"chat_id": chat_id, "text": text, "draft": True})
    config = telegram_registry.get_config(integration_id)
    if bool(result.get("ok")):
        await _log_platform_message(
            str(config.get("owner_user_id", "")).strip() or None,
            platform="telegram",
            platform_chat_id=str(chat_id),
            role="assistant",
            content=text,
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
    result = await integration.execute_tool("slack_send_message", {"channel": channel, "text": text})
    config = slack_registry.get_config(integration_id)
    if bool(result.get("ok")):
        await _log_platform_message(
            str(config.get("owner_user_id", "")).strip() or None,
            platform="slack",
            platform_chat_id=channel,
            role="assistant",
            content=text,
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
    result = await integration.execute_tool("discord_send_message", {"channel": channel, "text": text})
    config = discord_registry.get_config(integration_id)
    if bool(result.get("ok")):
        await _log_platform_message(
            str(config.get("owner_user_id", "")).strip() or None,
            platform="discord",
            platform_chat_id=channel,
            role="assistant",
            content=text,
            title=f"Discord {channel}",
            metadata={"integration_id": integration_id, "source": "send_message"},
        )
    return {"ok": bool(result.get("ok")), "result": result}


@app.post("/api/integrations/github/register/{integration_id}")
async def register_github_integration(
    integration_id: str,
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_get_current_user),
) -> dict[str, Any]:
    config = {
        "token": str(payload.get("token", "")).strip(),
        "webhook_secret": str(payload.get("webhook_secret", "")).strip(),
        "app_id": str(payload.get("app_id", "")).strip(),
        "owner_user_id": user["uid"],
    }
    integration = GitHubIntegration()
    connection = await integration.connect(config)
    github_registry.upsert(user["uid"], integration_id, integration, config)
    return {"connection": connection}


@app.post("/api/integrations/github/{integration_id}/test")
async def test_github_integration(
    integration_id: str,
    user: dict[str, Any] = Depends(_get_current_user),
) -> dict[str, Any]:
    integration = github_registry.get_github(user["uid"], integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="GitHub integration not found")
    return await integration.execute_tool("github_list_repos", {"per_page": 5})


@app.post("/api/integrations/github/{integration_id}/webhook")
async def github_webhook(integration_id: str, request: Request) -> dict[str, Any]:
    """Receive GitHub webhook events (push, PR, issue, etc.)."""
    candidates = github_registry.list_candidates(integration_id)
    if not candidates:
        raise HTTPException(status_code=404, detail="GitHub integration not found")

    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    selected_integration: GitHubIntegration | None = None
    for _owner_user_id, integration, config in candidates:
        webhook_secret = str(config.get("webhook_secret", "")).strip()
        if not webhook_secret:
            if selected_integration is None:
                selected_integration = integration
            continue
        if signature and integration.verify_webhook_signature(body, signature):
            selected_integration = integration
            break
    if selected_integration is None:
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    event_type = request.headers.get("X-GitHub-Event", "ping")
    return {"ok": True, "event": event_type, "action": payload.get("action"), "received": True}


# ── Cloud Agent Spawn endpoints ───────────────────────────────────────


@app.post("/api/agents/spawn")
async def spawn_agent_task(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_get_current_user),
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
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict[str, Any] = Depends(_get_current_user),
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
    user: dict[str, Any] = Depends(_get_current_user),
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
    user: dict[str, Any] = Depends(_get_current_user),
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
        )
        status = result.get("status", "completed")
        reply = f"✅ Task {status}: {instruction[:60]}"
    except asyncio.CancelledError:
        reply = "🛑 Task was interrupted."
    except Exception as exc:
        reply = f"❌ Task failed: {exc}"
    finally:
        runtime.task_running = False
    # Send result back to bot
    if platform == "telegram":
        integration = telegram_registry.get_telegram(integration_id)
        if integration:
            await integration.execute_tool("telegram_send_message", {"chat_id": chat_id, "text": reply})
    elif platform == "discord":
        integration = discord_registry.get_discord(integration_id)
        if integration:
            await integration.execute_tool("discord_send_message", {"channel": str(chat_id), "text": reply})


def _get_telegram_sender_id(update: dict[str, Any]) -> str:
    msg = update.get("message") or update.get("edited_message") or {}
    return str((msg.get("from") or {}).get("id", ""))


async def _handle_slash_command(
    text: str,
    owner_uid: str | None,
    platform: str,
    integration_id: str,
    chat_id: Any,
    ack_reaction: str = "",
) -> str | None:
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
            "/models — list & switch model\n"
            "/stream start|stop — live screenshots\n"
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
        return f"{state}\n🧠 Model: {model} ({provider})\n📋 Queued: {queued}{credits_info}"

    if cmd == "model":
        if not runtime:
            return "⚪ No active session."
        model = runtime.settings.get("model", "not set")
        provider = runtime.settings.get("provider", "")
        return f"🧠 Current model: *{model}* ({provider})"

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

    return f"❓ Unknown command: /{cmd}\nType /help for a list of commands."


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

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str) -> FileResponse:
        """Serve compiled frontend files in production."""
        candidate = (FRONTEND_DIST_DIR / full_path).resolve()
        try:
            candidate.relative_to(FRONTEND_DIST_DIR.resolve())
        except ValueError:
            return FileResponse(FRONTEND_DIST_DIR / "index.html")

        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
