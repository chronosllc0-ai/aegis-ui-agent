"""Aegis UI Navigator - FastAPI entrypoint."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from aegis_logging import setup_logging
from auth import router as auth_router, _verify_session
from backend.admin import admin_router
from backend.connectors.router import connector_router
from backend.database import get_session, init_db, create_tables, SupportThread, SupportMessage, UserConnection
from backend.credit_rates import CREDIT_RATES, get_tier
from backend.credit_service import check_credits, get_or_create_balance, get_usage_history, get_usage_summary
from backend.key_management import KeyManager
from backend.providers import get_provider, list_providers
from config import settings
from integrations.discord import DiscordIntegration
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
app.include_router(connector_router)

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
    """Kick off database initialization on application startup."""
    global db_init_task

    if db_init_task is None or db_init_task.done():
        db_init_task = asyncio.create_task(_initialize_database())


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


slack_registry = SlackRegistry()
discord_registry = DiscordRegistry()


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
            on_frame=lambda image_b64: _send_frame(websocket, image_b64),
            cancel_event=runtime.cancel_event,
            steering_context=runtime.steering_context,
            settings=runtime.settings,
            on_workflow_step=lambda step: _send_workflow_step(websocket, step),
        )
        await websocket.send_json({"type": "result", "data": result})
    except asyncio.CancelledError:
        logger.info("Navigation task cancelled for session %s", session_id)
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Navigation task failed for session %s", session_id)
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
                _start_navigation_task(websocket, runtime, session_id, instruction)
            elif action == "steer":
                runtime.steering_context.append(instruction)
                await _send_step(websocket, {"type": "steer", "content": f"Steering note added: {instruction}"})
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
                    else:
                        _start_navigation_task(websocket, runtime, session_id, transcript)
            elif action == "stop":
                runtime.cancel_event.set()
                break
            else:
                await websocket.send_json({"type": "error", "data": {"message": f"Unknown action: {action}"}})
    except WebSocketDisconnect:
        logger.info("Websocket disconnected")
    finally:
        if runtime.current_task is not None and not runtime.current_task.done():
            runtime.cancel_event.set()
            runtime.current_task.cancel()
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
    return {"ok": True, "result": result}


@app.post("/api/integrations/telegram/register/{integration_id}")
async def register_telegram_integration(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = {
        "bot_token": str(payload.get("bot_token", "")).strip(),
        "delivery_mode": str(payload.get("delivery_mode", "polling")).strip(),
        "webhook_url": str(payload.get("webhook_url", "")).strip(),
        "webhook_secret": str(payload.get("webhook_secret", "")).strip(),
    }
    integration = TelegramIntegration()
    connection = await integration.connect(config)
    telegram_registry.upsert(integration_id, integration, config)
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
    return {"ok": bool(result.get("ok")), "result": result}


@app.post("/api/integrations/slack/register/{integration_id}")
async def register_slack_integration(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = {
        "bot_token": str(payload.get("bot_token", "")).strip(),
        "oauth_token": str(payload.get("oauth_token", "")).strip(),
        "workspace": str(payload.get("workspace", "")).strip(),
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
    return {"ok": bool(result.get("ok")), "result": result}


@app.post("/api/integrations/discord/register/{integration_id}")
async def register_discord_integration(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = {
        "bot_token": str(payload.get("bot_token", "")).strip(),
        "guild_id": str(payload.get("guild_id", "")).strip(),
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
    return {"ok": bool(result.get("ok")), "result": result}


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
