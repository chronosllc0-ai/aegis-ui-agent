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
from uuid import uuid4

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
from backend.admin.runtime import set_runtime_inspector
from backend import database
from backend.automation import automation_router
from backend.agent_spawn import create_agent_task, get_task_actions, get_task_by_id, get_user_tasks, update_task_status
from backend.artifacts.router import artifact_router
from backend.connectors.router import connector_router
from backend.integrations.channel_runtime import ChannelRuntimeRegistry, DiscordChannelAdapter, SlackChannelAdapter, TelegramChannelAdapter
from backend.integrations.text_normalization import normalize_for_channel
from backend.gallery.router import gallery_router
from backend.memory.router import memory_router
from backend.modes import (
    MODE_LABELS,
    blocked_tools_for_mode,
    mode_definitions,
    normalize_agent_mode,
    parse_mode_runtime_event,
    serialize_mode_definition,
)
from backend.payments import payments_router
from backend.planner.executor_routes import executor_router
from backend.planner.router import planner_router
from backend.research.router import research_router
from backend.skills.router import skills_router
from backend.skills_hub.router import skills_hub_router
from backend.skills.runtime import resolve_runtime_skills
from backend.tasks.router import task_router as tasks_router
from backend.tasks.worker import BackgroundWorker
from backend.session_gateway import SessionEventHub
from backend.session_lanes import QueuedInstruction, SessionLaneQueue
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
from backend.heartbeat_pinger import HeartbeatPinger

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
session_events = SessionEventHub()
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
    _pinger.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cancel any outstanding background initialization tasks."""
    global db_init_task

    _pinger.stop()

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


channel_registry = ChannelRuntimeRegistry()
github_registry = GitHubRegistry()

# Maps authenticated user_uid -> active SessionRuntime (for bot command bridging)
_user_runtimes: dict[str, "SessionRuntime"] = {}
# Reverse index: session_id -> SessionRuntime for O(1) heartbeat dispatch
_session_runtimes: dict[str, "SessionRuntime"] = {}


def _runtime_snapshot() -> dict[str, Any]:
    route_snapshots = {item["session_id"]: item for item in session_events.snapshot()}
    sessions: list[dict[str, Any]] = []
    queued_total = 0

    for session_id, runtime in sorted(_session_runtimes.items(), key=lambda item: item[0]):
        queued_items = runtime.queued_instructions.snapshot()
        queue_depth = len(queued_items)
        queued_total += queue_depth
        route_snapshot = route_snapshots.get(session_id, {})
        sessions.append(
            {
                "session_id": session_id,
                "session_key": runtime.session_route_key or route_snapshot.get("session_key"),
                "user_uid": runtime.user_uid,
                "conversation_id": runtime.conversation_id or route_snapshot.get("conversation_id"),
                "task_running": runtime.task_running,
                "current_task_id": runtime.current_task_id,
                "current_request_id": runtime.current_request_id,
                "queue_depth": queue_depth,
                "queue_depth_by_lane": runtime.queued_instructions.depth_by_lane(),
                "queued_instructions": [
                    {
                        "queue_id": item.queue_id,
                        "instruction": item.instruction,
                        "lane": item.lane,
                        "source": item.source,
                        "metadata": item.metadata,
                        "enqueued_at": item.enqueued_at,
                    }
                    for item in queued_items
                ],
                "steering_context_depth": len(runtime.steering_context),
                "subagent_count": len(runtime.subagent_manager.list_agents()),
                "route": route_snapshot,
            }
        )

    return {
        "sessions": sessions,
        "summary": {
            "active_sessions": len(sessions),
            "queued_instructions": queued_total,
            "running_sessions": sum(1 for session in sessions if session["task_running"]),
            "session_routes": len(route_snapshots),
        },
        "routes": list(route_snapshots.values()),
    }


set_runtime_inspector(_runtime_snapshot)


def _get_channel_adapter(platform: str, integration_id: str) -> Any:
    return channel_registry.get_adapter(platform, integration_id)


def _get_channel_integration(platform: str, integration_id: str) -> Any:
    return channel_registry.get_integration(platform, integration_id)


def _get_channel_config(platform: str, integration_id: str) -> dict[str, Any]:
    return channel_registry.get_config(platform, integration_id)


def _channel_title(platform: str, destination: str) -> str:
    return f"{platform.title()} {destination}"


def _build_channel_command_metadata(platform: str, response: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if platform == "telegram" and isinstance(response.get("reply_markup"), dict):
        metadata["reply_markup"] = response["reply_markup"]
    if platform == "slack" and isinstance(response.get("blocks"), list):
        metadata["blocks"] = response["blocks"]
    if platform == "discord" and isinstance(response.get("components"), list):
        metadata["components"] = response["components"]
    return metadata


async def _send_channel_text(
    platform: str,
    integration_id: str,
    destination: str,
    text: str,
    *,
    metadata: dict[str, Any] | None = None,
    log_source: str = "send_message",
    draft: bool = False,
) -> dict[str, Any]:
    adapter = _get_channel_adapter(platform, integration_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    outgoing_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    parse_mode = str(outgoing_metadata.get("parse_mode", "")).strip() or None
    normalized_text, normalized_parse_mode = normalize_for_channel(text, channel=platform, parse_mode=parse_mode)
    if normalized_parse_mode:
        outgoing_metadata["parse_mode"] = normalized_parse_mode
    if draft:
        outgoing_metadata["draft"] = True
    result = await adapter.send_text(destination, normalized_text, metadata=outgoing_metadata)
    config = _get_channel_config(platform, integration_id)
    if bool(result.get("ok")):
        await _log_platform_message(
            str(config.get("owner_user_id", "")).strip() or None,
            platform=platform,
            platform_chat_id=destination,
            role="assistant",
            content=normalized_text,
            title=_channel_title(platform, destination),
            metadata={"integration_id": integration_id, "source": log_source, "draft": draft},
        )
    return result


def _channel_webhook_response(result: dict[str, Any]) -> dict[str, Any]:
    response = result.get("response") if isinstance(result, dict) else None
    if isinstance(response, dict):
        return response
    return {"ok": True, "result": result}


async def _dispatch_background_task_event(user_id: str, event: dict[str, Any]) -> None:
    """Publish background-task lifecycle events onto active primary websocket sessions."""
    if not user_id:
        return
    await session_events.publish_to_user(user_id, event, lane="background")


async def _heartbeat_dispatch(session_id: str, instruction: str) -> None:
    """Run or queue scheduled automations on the active primary session websocket."""
    runtime = _session_runtimes.get(session_id)
    if runtime is None or runtime.websocket is None:
        logger.info("Heartbeat dispatch (no active runtime): session=%s task=%s", session_id, instruction)
        return

    logger.info("Heartbeat dispatch matched runtime uid=%s session=%s task=%s", runtime.user_uid, session_id, instruction)
    await session_events.publish_to_session(
        session_id,
        {
            "type": "heartbeat_triggered",
            "data": {
                "instruction": instruction,
                "state": "queued" if runtime.task_running else "starting",
            },
        },
        lane="heartbeat",
    )
    if runtime.task_running:
        runtime.queued_instructions.enqueue(
            instruction,
            lane="heartbeat",
            source="heartbeat",
            metadata={"session_id": session_id},
        )
        await _send_step(
            runtime.websocket,
            {
                "type": "queue",
                "content": f"Automation queued: {instruction}",
            },
            runtime=runtime,
            session_id=session_id,
        )
        return

    runtime.current_request_id = f"heartbeat:{uuid4()}"
    runtime.current_task_id = str(uuid4())
    runtime.current_frontend_task_id = runtime.current_task_id
    await _log_web_message(
        runtime,
        session_id,
        "user",
        instruction,
        title=instruction[:200],
        metadata={"source": "heartbeat", "action": "automation_dispatch"},
    )
    _start_navigation_task(runtime.websocket, runtime, session_id, instruction)


_pinger = HeartbeatPinger(dispatch=_heartbeat_dispatch, interval_seconds=60)
background_worker.set_event_sink(_dispatch_background_task_event)

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
        self.queued_instructions = SessionLaneQueue()
        self.settings: dict[str, Any] = {}
        self.conversation_id: str | None = None
        self.user_uid: str | None = None
        self.session_id: str | None = None
        self.websocket: WebSocket | None = None
        self.session_route_key: str | None = None
        # Pending user-input futures keyed by request_id
        self.pending_user_inputs: dict[str, asyncio.Future[str]] = {}
        # Tracks the frontend-generated task UUID for the currently active navigate action.
        # Sent by the client in spawn_subagent so sub-agents can be scoped to the right parent task.
        self.current_frontend_task_id: str | None = None
        self.current_request_id: str | None = None
        self.current_task_id: str | None = None
        self.completed_task_ids: set[str] = set()
        self.request_idempotency: dict[str, tuple[float, dict[str, Any]]] = {}
        # Sub-agent manager — created lazily on first spawn
        from subagent_runtime import SubAgentManager
        self.subagent_manager: SubAgentManager = SubAgentManager()

    def get_idempotent_ack(self, request_id: str) -> dict[str, Any] | None:
        """Return cached idempotent ack payload for request_id when available."""
        cached = self.request_idempotency.get(request_id)
        return cached[1] if cached else None

    def remember_idempotent_ack(self, request_id: str, payload: dict[str, Any], *, max_entries: int = 256) -> None:
        """Store idempotent ack payload and prune old entries to prevent leaks."""
        self.request_idempotency[request_id] = (_time.monotonic(), payload)
        if len(self.request_idempotency) <= max_entries:
            return
        # Keep the most-recent entries only.
        oldest = sorted(self.request_idempotency.items(), key=lambda item: item[1][0])[: len(self.request_idempotency) - max_entries]
        for stale_request_id, _ in oldest:
            self.request_idempotency.pop(stale_request_id, None)


def _merge_runtime_settings(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge websocket config payload with defaults without dropping prior settings."""
    merged = {**current, **incoming}
    provider = str(merged.get("provider", "")).strip().lower()
    if not provider:
        # Use server-configured default (DEFAULT_PROVIDER env var).
        # Defaults to the Chronos gateway (OpenRouter). Override with e.g. DEFAULT_PROVIDER=google.
        merged["provider"] = settings.DEFAULT_PROVIDER or "chronos"
    model = str(merged.get("model", "")).strip()
    if not model:
        merged["model"] = settings.DEFAULT_MODEL or "nvidia/nemotron-3-super-120b-a12b:free"
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
    task_id: str | None = None,
    frontend_task_id: str | None = None,
) -> None:
    """Send workflow graph step payload to frontend."""
    await websocket.send_json({"type": "workflow_step", "data": workflow_step})
    parsed_mode_event, parse_error = parse_mode_runtime_event(workflow_step)
    if parsed_mode_event is not None:
        mode_event_payload = {
            **parsed_mode_event,
            "task_id": task_id,
            "frontend_task_id": frontend_task_id,
        }
        await websocket.send_json({"type": "mode_event", "data": mode_event_payload})
        if parsed_mode_event.get("event_name") == "mode_transition":
            await websocket.send_json(
                {
                    "type": "mode_transition",
                    "data": {
                        **parsed_mode_event.get("payload", {}),
                        "task_id": task_id,
                        "frontend_task_id": frontend_task_id,
                    },
                }
            )
        if parsed_mode_event.get("event_name") == "final_synthesis":
            await websocket.send_json(
                {
                    "type": "final_synthesis",
                    "data": {
                        **parsed_mode_event.get("payload", {}),
                        "task_id": task_id,
                        "frontend_task_id": frontend_task_id,
                    },
                }
            )
    elif parse_error and isinstance(workflow_step, dict) and workflow_step.get("event_name"):
        await websocket.send_json(
            {
                "type": "mode_event_parse_failed",
                "data": {
                    "error": parse_error,
                    "raw_event_name": str(workflow_step.get("event_name", "")),
                },
            }
        )
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


async def _safe_ws_send(
    websocket: WebSocket,
    payload: dict[str, Any],
    *,
    request_id: str | None = None,
    task_id: str | None = None,
    ws_session_id: str | None = None,
    phase: str = "send",
) -> bool:
    """Send a websocket payload and emit structured diagnostics on failures."""
    try:
        await websocket.send_json(payload)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "ws_send_failed request_id=%s task_id=%s ws_session_id=%s phase=%s outcome=error error_code=E_SOCKET_SEND_FAILED error=%s",
            request_id or "",
            task_id or "",
            ws_session_id or "",
            phase,
            exc,
        )
        return False


def _normalize_start_metadata(raw_metadata: object) -> dict[str, Any]:
    """Return a normalized metadata object without mutating inbound payloads."""
    if not isinstance(raw_metadata, dict):
        return {}
    allowed_keys = {
        "frontend_task_id",
        "agent_mode",
        "task_label",
        "task_label_source",
        "source",
        "target_subagents",
    }
    normalized: dict[str, Any] = {}
    for key, value in raw_metadata.items():
        key_str = str(key)
        if key_str not in allowed_keys:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            normalized[key_str] = value
        elif isinstance(value, list):
            normalized[key_str] = [item for item in value if isinstance(item, (str, int, float, bool))]
    return normalized


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
            session_events.bind_conversation(session_id, conv.id)
            await append_message(
                db,
                conv.id,
                role,
                content,
                metadata=metadata,
                title_candidate=title_candidate,
            )
            break
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist web message to DB for session %s: %s", session_id, exc)


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
        integration = _get_channel_integration("telegram", str(integration_id))
        if integration:
            asyncio.create_task(integration.send_photo(chat_id, image_b64))
    elif platform == "discord":
        integration = _get_channel_integration("discord", str(integration_id))
        if integration:
            channel = str(sub.get("channel_id", chat_id) or chat_id)
            asyncio.create_task(
                integration.execute_tool(
                    "discord_send_image",
                    {"channel": channel, "image_b64": image_b64},
                )
            )


def _start_navigation_task(websocket: WebSocket, runtime: SessionRuntime, session_id: str, instruction: str) -> None:
    """Create and store the background navigation task for the current session."""
    runtime.current_task = asyncio.create_task(
        _run_navigation_task(
            websocket,
            runtime,
            session_id,
            instruction,
            request_id=runtime.current_request_id or "",
            task_id=runtime.current_task_id or str(uuid4()),
        )
    )
    def _task_done_callback(task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            logger.info("Navigation task cancellation finalized for session %s", session_id)
        except Exception:
            logger.exception("Navigation background task crashed for session %s", session_id)
        finally:
            if runtime.current_task is task:
                runtime.current_task = None

    runtime.current_task.add_done_callback(_task_done_callback)


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
    """Reject control actions while idle; only navigate can start a new run."""
    await websocket.send_json(
        {
            "type": "error",
            "data": {
                "message": f"{action}: no active task. Use navigate to start a new task.",
            },
        }
    )
    await _log_web_message(
        runtime,
        session_id,
        "assistant",
        f"Rejected idle {action} action. Navigate is required to start a task.",
        metadata={
            "source": "websocket",
            "action": f"idle_{action}_rejected",
            "task_label": task_label,
            "title_candidate": title_candidate,
            "client": client_metadata or {},
        },
    )


async def _start_next_queued_task_if_ready(websocket: WebSocket, runtime: SessionRuntime, session_id: str) -> None:
    """Start the next queued task when no task is active and cancellation is not pending."""
    if runtime.task_running or runtime.cancel_event.is_set() or not runtime.queued_instructions:
        return

    queued_instruction = runtime.queued_instructions.pop_next()
    if queued_instruction is None:
        return
    await _send_step(
        websocket,
        {
            "type": "queue",
            "content": f"Starting queued task ({queued_instruction.lane}): {queued_instruction.instruction}",
        },
        runtime=runtime,
        session_id=session_id,
    )
    await _log_web_message(
        runtime,
        session_id,
        "user",
        queued_instruction.instruction,
        title=queued_instruction.instruction[:200],
        metadata={
            "source": queued_instruction.source,
            "action": "queue",
            "lane": queued_instruction.lane,
            "queue_metadata": queued_instruction.metadata,
        },
    )
    _start_navigation_task(websocket, runtime, session_id, queued_instruction.instruction)


async def _run_navigation_task(
    websocket: WebSocket,
    runtime: SessionRuntime,
    session_id: str,
    instruction: str,
    *,
    request_id: str,
    task_id: str,
) -> None:
    """Execute a single navigation task and optionally schedule one queued follow-up."""
    terminal_event_sent = False

    async def _emit_terminal_result(*, summary: str, status: str) -> None:
        nonlocal terminal_event_sent
        if terminal_event_sent:
            return
        terminal_event_sent = True
        await _safe_ws_send(
            websocket,
            {"type": "task_state", "data": {"task_id": task_id, "state": status, "timestamp": _time.time()}},
            request_id=request_id,
            task_id=task_id,
            ws_session_id=session_id,
            phase="task_state_terminal",
        )
        await _safe_ws_send(
            websocket,
            {"type": "task_result", "data": {"task_id": task_id, "summary": summary, "timestamp": _time.time()}},
            request_id=request_id,
            task_id=task_id,
            ws_session_id=session_id,
            phase="task_result_terminal",
        )

    async def callback(step: dict[str, Any]) -> None:
        await _send_step(websocket, step, runtime=runtime, session_id=session_id)
        step_type = str(step.get("type") or "").lower()
        task_state = "tool_call" if step_type in {"tool-call", "tool_call"} else "running"
        await _safe_ws_send(
            websocket,
            {
                "type": "task_state",
                "data": {
                    "task_id": task_id,
                    "state": task_state,
                    "detail": str(step.get("content") or step_type or "task_update"),
                    "timestamp": _time.time(),
                },
            },
            request_id=request_id,
            task_id=task_id,
            ws_session_id=session_id,
            phase="task_state",
        )

    runtime.task_running = True
    runtime.cancel_event.clear()
    _normalize_runtime_mode(runtime.settings)
    await _safe_ws_send(
        websocket,
        {"type": "task_state", "data": {"task_id": task_id, "state": "running", "timestamp": _time.time()}},
        request_id=request_id,
        task_id=task_id,
        ws_session_id=session_id,
        phase="task_state_running",
    )

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
            parent_task_id=runtime.current_frontend_task_id,
        )
        # Send updated agent list to frontend on the primary session websocket.
        subagent_list_event = {
            "type": "subagent_list",
            "data": {"agents": runtime.subagent_manager.list_agents()},
        }
        await websocket.send_json(subagent_list_event)
        return sub_id

    async def _on_message_subagent(sub_id: str, message: str) -> bool:
        return await runtime.subagent_manager.send_message(sub_id, message)

    try:
        max_duration_seconds = int(runtime.settings.get("model_timeout_seconds") or settings.NAVIGATION_TASK_TIMEOUT_SECONDS)
        max_tool_calls = int(runtime.settings.get("max_tool_calls") or settings.NAVIGATION_MAX_TOOL_CALLS)
        effective_runtime_settings = {
            "max_tool_calls": max_tool_calls,
            "model_timeout_seconds": max_duration_seconds,
            **runtime.settings,
        }
        result = await asyncio.wait_for(
            _get_orchestrator().execute_task(
            session_id=session_id,
            instruction=instruction,
            on_step=callback,
            on_frame=lambda image_b64: _on_frame_combined(websocket, image_b64, runtime.user_uid),
            cancel_event=runtime.cancel_event,
            steering_context=runtime.steering_context,
            on_workflow_step=lambda step: _send_workflow_step(
                websocket,
                step,
                runtime=runtime,
                session_id=session_id,
                task_id=task_id,
                frontend_task_id=runtime.current_frontend_task_id,
            ),
            user_uid=runtime.user_uid,
            on_user_input=_on_user_input,
            on_reasoning_delta=_on_reasoning_delta,
            on_spawn_subagent=_on_spawn_subagent,
            on_message_subagent=_on_message_subagent,
            settings=effective_runtime_settings,
        ),
            timeout=max_duration_seconds,
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
            error_already_emitted = bool(result.get("error_already_emitted")) if isinstance(result, dict) else False
            await _safe_ws_send(
                websocket,
                {
                    "type": "task_error",
                    "data": {
                        "task_id": task_id,
                        "request_id": request_id,
                        "code": "E_TASK_FAILED",
                        "message": error_msg,
                        "retryable": True,
                        "error_already_emitted": error_already_emitted,
                    },
                },
                request_id=request_id,
                task_id=task_id,
                ws_session_id=session_id,
                phase="task_error",
            )
            if not error_already_emitted:
                await _safe_ws_send(
                    websocket,
                    {"type": "error", "data": {"message": error_msg}},
                    request_id=request_id,
                    task_id=task_id,
                    ws_session_id=session_id,
                    phase="legacy_error",
                )
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
        terminal_state = "succeeded" if result_status == "completed" else "failed"
        await _emit_terminal_result(
            summary=str((result or {}).get("summary") or (result or {}).get("error") or result_status),
            status=terminal_state,
        )
        await _safe_ws_send(websocket, {"type": "result", "data": result}, request_id=request_id, task_id=task_id, ws_session_id=session_id, phase="legacy_result")
    except asyncio.CancelledError:
        logger.info("Navigation task cancelled for session %s", session_id)
        await _emit_terminal_result(summary="Task cancelled", status="cancelled")
        raise
    except asyncio.TimeoutError:
        await _safe_ws_send(
            websocket,
            {"type": "task_error", "data": {"task_id": task_id, "request_id": request_id, "code": "E_TASK_TIMEOUT", "message": "Task execution timed out", "retryable": True}},
            request_id=request_id,
            task_id=task_id,
            ws_session_id=session_id,
            phase="task_timeout_error",
        )
        await _emit_terminal_result(summary="Task timed out", status="failed")
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
        await _safe_ws_send(
            websocket,
            {"type": "task_error", "data": {"task_id": task_id, "request_id": request_id, "code": "E_TASK_EXCEPTION", "message": str(exc), "retryable": True}},
            request_id=request_id,
            task_id=task_id,
            ws_session_id=session_id,
            phase="task_exception_error",
        )
        await _emit_terminal_result(summary=str(exc), status="failed")
        await _safe_ws_send(websocket, {"type": "error", "data": {"message": str(exc)}}, request_id=request_id, task_id=task_id, ws_session_id=session_id, phase="legacy_error_exception")
        await _safe_ws_send(websocket, {"type": "result", "data": {"status": "failed", "instruction": instruction, "steps": []}}, request_id=request_id, task_id=task_id, ws_session_id=session_id, phase="legacy_result_exception")
    finally:
        runtime.task_running = False
        runtime.completed_task_ids.add(task_id)

    await _start_next_queued_task_if_ready(websocket, runtime, session_id)


# ── WebSocket navigation endpoint ────────────────────────────────────


@app.websocket("/ws/agent")
@app.websocket("/ws/navigate")
async def websocket_navigate(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time agent sessions.

    Accepts both /ws/agent (new) and /ws/navigate (legacy alias).
    """
    await websocket.accept()
    session_id = await live_manager.create_session()
    runtime = SessionRuntime()
    runtime.user_uid = _extract_websocket_user_uid(websocket)
    runtime.session_id = session_id
    runtime.websocket = websocket
    session_route = session_events.register(
        session_id,
        user_uid=runtime.user_uid,
        send=lambda payload: _safe_ws_send(websocket, payload, ws_session_id=session_id, phase="session_event"),
    )
    runtime.session_route_key = session_route.session_key
    if runtime.user_uid:
        _user_runtimes[runtime.user_uid] = runtime
    # O(1) reverse index for heartbeat dispatch
    _session_runtimes[session_id] = runtime

    try:
        await _get_orchestrator().executor.ensure_browser()
        await _send_initial_frame(websocket)

        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            # Normalize action aliases → canonical internal names
            if action in {"navigate", "task", "chat", "message"}:
                action = "navigate_start"
            if action == "stop":
                action = "stop_task"
            raw_instruction = data.get("instruction")
            raw_prompt = data.get("prompt")
            instruction = str(
                raw_instruction
                if raw_instruction is not None
                else raw_prompt
                if raw_prompt is not None
                else ""
            ).strip()
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
            client_metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
            task_label = str(client_metadata.get("task_label", "")).strip()
            title_candidate = task_label or instruction

            if action in {"steer", "interrupt", "queue", "dequeue"}:
                await _safe_ws_send(
                    websocket,
                    {
                        "type": "task_error",
                        "data": {
                            "request_id": str(data.get("request_id") or ""),
                            "task_id": runtime.current_task_id,
                            "code": "E_BAD_PAYLOAD",
                            "message": f"{action} is disabled. Use navigate_start as the sole command action.",
                            "retryable": False,
                        },
                    },
                    request_id=runtime.current_request_id,
                    task_id=runtime.current_task_id,
                    ws_session_id=session_id,
                    phase="disabled_runtime_control",
                )
                continue

            if action == "navigate_start":
                request_id = str(data.get("request_id") or "").strip()
                if not request_id:
                    request_id = str(uuid4())
                if not instruction:
                    logger.info(
                        "navigate_start request_id=%s task_id=%s ws_session_id=%s phase=validate outcome=rejected error_code=E_BAD_PAYLOAD",
                        request_id,
                        "",
                        session_id,
                    )
                    await _safe_ws_send(
                        websocket,
                        {"type": "navigate_ack", "data": {"request_id": request_id, "task_id": None, "accepted": False, "reason": "E_BAD_PAYLOAD"}},
                        request_id=request_id,
                        ws_session_id=session_id,
                        phase="navigate_ack_bad_payload",
                    )
                    await _safe_ws_send(
                        websocket,
                        {"type": "task_error", "data": {"request_id": request_id, "code": "E_BAD_PAYLOAD", "message": "navigate_start: instruction is required", "retryable": True}},
                        request_id=request_id,
                        ws_session_id=session_id,
                        phase="navigate_error_bad_payload",
                    )
                    continue

                cached_ack = runtime.get_idempotent_ack(request_id)
                if cached_ack is not None:
                    logger.info(
                        "navigate_start request_id=%s task_id=%s ws_session_id=%s phase=ack outcome=idempotent",
                        request_id,
                        cached_ack.get("task_id"),
                        session_id,
                    )
                    await _safe_ws_send(
                        websocket,
                        {"type": "navigate_ack", "data": cached_ack},
                        request_id=request_id,
                        task_id=cached_ack.get("task_id"),
                        ws_session_id=session_id,
                        phase="navigate_ack_idempotent",
                    )
                    continue
                if runtime.task_running:
                    busy_task_id = runtime.current_task_id or ""
                    ack_payload = {"request_id": request_id, "task_id": busy_task_id, "accepted": False, "reason": "E_START_REJECTED_BUSY"}
                    runtime.remember_idempotent_ack(request_id, ack_payload)
                    logger.info(
                        "navigate_start request_id=%s task_id=%s ws_session_id=%s phase=validate outcome=rejected error_code=E_START_REJECTED_BUSY",
                        request_id,
                        busy_task_id,
                        session_id,
                    )
                    await _safe_ws_send(websocket, {"type": "navigate_ack", "data": ack_payload}, request_id=request_id, task_id=busy_task_id, ws_session_id=session_id, phase="navigate_ack_busy")
                    await _safe_ws_send(
                        websocket,
                        {"type": "task_error", "data": {"request_id": request_id, "task_id": busy_task_id, "code": "E_START_REJECTED_BUSY", "message": "Task already running", "retryable": True}},
                        request_id=request_id,
                        task_id=busy_task_id,
                        ws_session_id=session_id,
                        phase="navigate_error_busy",
                    )
                    continue
                task_id = str(uuid4())
                runtime.current_request_id = request_id
                runtime.current_task_id = task_id
                logger.info(
                    "navigate_start request_id=%s task_id=%s ws_session_id=%s phase=ack outcome=accepted",
                    request_id,
                    task_id,
                    session_id,
                )
                ack_payload = {"request_id": request_id, "task_id": task_id, "accepted": True}
                runtime.remember_idempotent_ack(request_id, ack_payload)
                await _safe_ws_send(
                    websocket,
                    {"type": "navigate_ack", "data": ack_payload},
                    request_id=request_id,
                    task_id=task_id,
                    ws_session_id=session_id,
                    phase="navigate_ack_accept",
                )
                await _safe_ws_send(
                    websocket,
                    {"type": "task_state", "data": {"task_id": task_id, "state": "queued", "timestamp": _time.time()}},
                    request_id=request_id,
                    task_id=task_id,
                    ws_session_id=session_id,
                    phase="task_queued",
                )
                # Track the frontend-generated task ID so sub-agents can be scoped to the right parent task.
                # If the client does not provide one, synthesize a server-side fallback.
                normalized_metadata = _normalize_start_metadata(data.get("metadata"))
                frontend_task_id = str(normalized_metadata.get("frontend_task_id", "") or "").strip() or task_id
                runtime.current_frontend_task_id = frontend_task_id
                server_metadata = {
                    **normalized_metadata,
                    "frontend_task_id": frontend_task_id,
                    "agent_mode": str(normalized_metadata.get("agent_mode", "") or active_mode),
                }
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
                        "client": server_metadata,
                    },
                )
                if runtime.conversation_id:
                    await websocket.send_json({"type": "conversation_id", "data": {"conversation_id": runtime.conversation_id}})
                _start_navigation_task(websocket, runtime, session_id, instruction)
            elif action == "stop_task":
                requested_task_id = str(data.get("task_id") or "").strip()
                if runtime.current_task is None or runtime.current_task.done():
                    await _safe_ws_send(
                        websocket,
                        {"type": "task_error", "data": {"task_id": requested_task_id or runtime.current_task_id, "code": "E_BAD_PAYLOAD", "message": "No running task to stop", "retryable": False}},
                        request_id=runtime.current_request_id,
                        task_id=requested_task_id or runtime.current_task_id,
                        ws_session_id=session_id,
                        phase="stop_task_idle",
                    )
                    continue
                runtime.cancel_event.set()
                runtime.current_task.cancel()
                await _safe_ws_send(
                    websocket,
                    {"type": "task_state", "data": {"task_id": runtime.current_task_id, "state": "cancelled", "timestamp": _time.time()}},
                    request_id=runtime.current_request_id,
                    task_id=runtime.current_task_id,
                    ws_session_id=session_id,
                    phase="stop_task_cancelled",
                )
            elif action == "steer":
                if not instruction:
                    await websocket.send_json({"type": "error", "data": {"message": "steer: instruction is required"}})
                    continue
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
                    metadata={"source": "websocket", "action": "steer", "client": client_metadata},
                )
            elif action == "interrupt":
                if not instruction:
                    await websocket.send_json({"type": "error", "data": {"message": "interrupt: instruction is required"}})
                    continue
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
                    metadata={"source": "websocket", "action": "interrupt", "client": client_metadata},
                )
                _start_navigation_task(websocket, runtime, session_id, instruction)
            elif action == "queue":
                if not instruction:
                    await websocket.send_json({"type": "error", "data": {"message": "queue: instruction is required"}})
                    continue
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
                runtime.queued_instructions.enqueue(
                    instruction,
                    lane="interactive",
                    source="websocket",
                    metadata={"client": client_metadata, "task_label": task_label},
                )
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
                    metadata={"source": "websocket", "action": "queue", "client": client_metadata},
                )
            elif action == "dequeue":
                raw_index = data.get("index", -1)
                try:
                    index = int(raw_index)
                except (TypeError, ValueError):
                    await websocket.send_json({"type": "error", "data": {"message": "Invalid queue index"}})
                    continue

                removed = runtime.queued_instructions.remove_at(index)
                if removed is not None:
                    await _send_step(
                        websocket,
                        {"type": "queue", "content": f"Removed queued instruction: {removed.instruction}"},
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
                enabled_skill_ids = candidate_settings.get("enabled_skill_ids")
                if enabled_skill_ids is not None:
                    if not isinstance(enabled_skill_ids, list) or any(not isinstance(item, str) for item in enabled_skill_ids):
                        await websocket.send_json({"type": "error", "data": {"message": "Invalid config payload: enabled_skill_ids must be a list of strings"}})
                        continue
                    resolved_context = await resolve_runtime_skills(runtime.user_uid, enabled_skill_ids)
                    candidate_settings = {
                        **candidate_settings,
                        **resolved_context.as_settings_fragment(),
                    }
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
                await _safe_ws_send(websocket, {"type": "pong"}, ws_session_id=session_id, phase="pong")
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

                # Use parent_task_id from the client payload (frontend-generated task UUID),
                # falling back to the last known task ID from the navigate action.
                fe_task_id = str(data.get("parent_task_id", "") or "").strip() or runtime.current_frontend_task_id
                sub_id = await runtime.subagent_manager.spawn(
                    instruction=sub_instruction,
                    model=sub_model,
                    parent_user_uid=runtime.user_uid,
                    orchestrator=_get_orchestrator(),
                    parent_settings=runtime.settings,
                    send_to_parent=_sub_send,
                    on_user_input=None,  # sub-agents don't forward user-input to parent for now
                    parent_task_id=fe_task_id,
                )
                await websocket.send_json({
                    "type": "subagent_spawned",
                    "data": {
                        "sub_id": sub_id,
                        "instruction": sub_instruction,
                        "model": sub_model,
                        "parent_task_id": fe_task_id,
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
        _session_runtimes.pop(session_id, None)
        session_events.unregister(session_id)
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
    adapter = _get_channel_adapter("telegram", integration_id)
    integration = _get_channel_integration("telegram", integration_id)
    if adapter is None or integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    config = _get_channel_config("telegram", integration_id)
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if hasattr(integration, "validate_webhook_secret"):
        if not integration.validate_webhook_secret(secret):
            raise HTTPException(status_code=403, detail="Invalid secret token")
    else:
        expected_secret = str(config.get("webhook_secret", ""))
        if expected_secret and secret != expected_secret:
            raise HTTPException(status_code=403, detail="Invalid secret token")

    update = await request.json()
    result = await adapter.handle_event(update, dict(request.headers))
    owner_user_id = str(config.get("owner_user_id", "")).strip() or None

    callback_mode_raw = adapter.extract_mode_selection(update)
    if callback_mode_raw is not None:
        callback_message = update.get("callback_query", {}).get("message", {})
        callback_chat_id = (callback_message.get("chat") or {}).get("id")
        callback_destination = str(callback_chat_id) if callback_chat_id is not None else None
        if not owner_user_id:
            if callback_destination:
                await _send_channel_text(
                    "telegram",
                    integration_id,
                    callback_destination,
                    "⚠️ Mode switching is only available for the owner session.",
                    log_source="mode_switch",
                )
            return _channel_webhook_response(result)
        runtime = _user_runtimes.get(owner_user_id)
        if not runtime:
            if callback_destination:
                await _send_channel_text(
                    "telegram",
                    integration_id,
                    callback_destination,
                    "⚠️ No active session. Start a session first.",
                    log_source="mode_switch",
                )
            return _channel_webhook_response(result)
        selected_mode, mode_valid, mode_error = _apply_runtime_mode_update(runtime, callback_mode_raw)
        if not mode_valid:
            if callback_destination:
                await _send_channel_text(
                    "telegram",
                    integration_id,
                    callback_destination,
                    f"❌ {mode_error}",
                    log_source="mode_switch",
                )
            return _channel_webhook_response(result)
        if callback_destination:
            await _send_channel_text(
                "telegram",
                integration_id,
                callback_destination,
                f"✅ Mode switched to *{MODE_LABELS.get(selected_mode, selected_mode.title())}*",
                log_source="mode_switch",
            )
        return _channel_webhook_response(result)

    inbound = adapter.extract_message(update)
    chat_id = inbound.destination
    text_content = inbound.text
    platform_message_id = inbound.message_id

    if chat_id and text_content and text_content.startswith("/"):
        bot_cfg = _bot_configs.get(f"telegram:{integration_id}", {})
        allow_from = bot_cfg.get("allow_from", [])
        if allow_from:
            sender_id = str(_get_telegram_sender_id(update))
            if sender_id not in allow_from:
                return _channel_webhook_response(result)
        ack_reaction = bot_cfg.get("ack_reaction", "")
        cmd_response = await _handle_slash_command(
            text=text_content,
            owner_uid=owner_user_id,
            platform="telegram",
            integration_id=integration_id,
            chat_id=chat_id,
            ack_reaction=ack_reaction,
        )
        if isinstance(cmd_response, dict):
            await _send_channel_text(
                "telegram",
                integration_id,
                chat_id,
                str(cmd_response.get("text", "")),
                metadata=_build_channel_command_metadata("telegram", cmd_response),
                log_source="slash_command",
            )
        elif cmd_response:
            await _send_channel_text(
                "telegram",
                integration_id,
                chat_id,
                cmd_response,
                log_source="slash_command",
            )
        return _channel_webhook_response(result)

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
    return _channel_webhook_response(result)



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
    channel_registry.upsert("telegram", integration_id, TelegramChannelAdapter(integration), config)
    if connection.get("connected"):
        asyncio.create_task(_register_telegram_commands(integration))
    return {"ok": True, "connection": connection}



@app.post("/api/integrations/telegram/{integration_id}/test")
async def test_telegram_integration(integration_id: str) -> dict[str, Any]:
    adapter = _get_channel_adapter("telegram", integration_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    result = await adapter.test_connection()
    return {"ok": bool(result.get("ok")), "result": result}



@app.post("/api/integrations/telegram/{integration_id}/send_message")
async def telegram_send_message(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        chat_id = int(payload.get("chat_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    text = str(payload.get("text", "")).strip()
    parse_mode = str(payload.get("parse_mode", "")).strip() or None
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    metadata: dict[str, Any] = {}
    if parse_mode:
        metadata["parse_mode"] = parse_mode
    if isinstance(payload.get("reply_markup"), dict):
        metadata["reply_markup"] = payload["reply_markup"]
    result = await _send_channel_text(
        "telegram",
        integration_id,
        str(chat_id),
        text,
        metadata=metadata,
        log_source="send_message",
    )
    return {"ok": bool(result.get("ok")), "result": result}



@app.post("/api/integrations/telegram/{integration_id}/send_draft")
async def telegram_send_draft(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        chat_id = int(payload.get("chat_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid chat_id")
    text = str(payload.get("text", "")).strip()
    parse_mode = str(payload.get("parse_mode", "")).strip() or None
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    metadata: dict[str, Any] = {}
    if parse_mode:
        metadata["parse_mode"] = parse_mode
    if isinstance(payload.get("reply_markup"), dict):
        metadata["reply_markup"] = payload["reply_markup"]
    result = await _send_channel_text(
        "telegram",
        integration_id,
        str(chat_id),
        text,
        metadata=metadata,
        log_source="send_message",
        draft=True,
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
    channel_registry.upsert("slack", integration_id, SlackChannelAdapter(integration), config)
    return {"ok": True, "connection": connection}



@app.post("/api/integrations/slack/webhook/{integration_id}")
async def slack_webhook(integration_id: str, request: Request) -> dict[str, Any]:
    """Handle Slack events/interactions and route shared slash commands."""
    adapter = _get_channel_adapter("slack", integration_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    payload = await request.json()
    result = await adapter.handle_event(payload, dict(request.headers))
    owner_user_id = str(_get_channel_config("slack", integration_id).get("owner_user_id", "")).strip() or None

    selected_mode_raw = adapter.extract_mode_selection(payload if isinstance(payload, dict) else {})
    if selected_mode_raw:
        channel = str(payload.get("channel", {}).get("id") or payload.get("channel_id") or "").strip()
        if not owner_user_id:
            if channel:
                await _send_channel_text(
                    "slack",
                    integration_id,
                    channel,
                    "⚠️ Mode switching is only available for the owner session.",
                    log_source="mode_switch",
                )
            return _channel_webhook_response(result)
        runtime = _user_runtimes.get(owner_user_id)
        if not runtime:
            if channel:
                await _send_channel_text(
                    "slack",
                    integration_id,
                    channel,
                    "⚠️ No active session. Start a session first.",
                    log_source="mode_switch",
                )
            return _channel_webhook_response(result)
        selected_mode, mode_valid, mode_error = _apply_runtime_mode_update(runtime, selected_mode_raw)
        if not mode_valid:
            if channel:
                await _send_channel_text(
                    "slack",
                    integration_id,
                    channel,
                    f"❌ {mode_error}",
                    log_source="mode_switch",
                )
            return _channel_webhook_response(result)
        if channel:
            await _send_channel_text(
                "slack",
                integration_id,
                channel,
                f"✅ Mode switched to *{MODE_LABELS.get(selected_mode, selected_mode.title())}*",
                log_source="mode_switch",
            )
        return _channel_webhook_response(result)

    inbound = adapter.extract_message(payload if isinstance(payload, dict) else {})
    channel = inbound.destination
    text_content = inbound.text
    platform_message_id = inbound.message_id
    if channel and text_content and text_content.startswith("/"):
        cmd_response = await _handle_slash_command(
            text=text_content,
            owner_uid=owner_user_id,
            platform="slack",
            integration_id=integration_id,
            chat_id=channel,
        )
        if isinstance(cmd_response, dict):
            await _send_channel_text(
                "slack",
                integration_id,
                channel,
                str(cmd_response.get("text", "")),
                metadata=_build_channel_command_metadata("slack", cmd_response),
                log_source="slash_command",
            )
        elif cmd_response:
            await _send_channel_text(
                "slack",
                integration_id,
                channel,
                cmd_response,
                log_source="slash_command",
            )
        return _channel_webhook_response(result)

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
    return _channel_webhook_response(result)



@app.post("/api/integrations/slack/{integration_id}/test")
async def test_slack_integration(integration_id: str) -> dict[str, Any]:
    adapter = _get_channel_adapter("slack", integration_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    result = await adapter.test_connection()
    return {"ok": bool(result.get("ok")), "result": result}



@app.post("/api/integrations/slack/{integration_id}/send_message")
async def slack_send_message(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    channel = str(payload.get("channel", "")).strip()
    text = str(payload.get("text", "")).strip()
    if not channel:
        raise HTTPException(status_code=400, detail="Channel is required")
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    metadata: dict[str, Any] = {}
    if isinstance(payload.get("blocks"), list):
        metadata["blocks"] = payload["blocks"]
    if payload.get("thread_ts"):
        metadata["thread_ts"] = str(payload["thread_ts"])
    result = await _send_channel_text(
        "slack",
        integration_id,
        channel,
        text,
        metadata=metadata,
        log_source="send_message",
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
    channel_registry.upsert("discord", integration_id, DiscordChannelAdapter(integration), config)
    return {"ok": True, "connection": connection}



@app.post("/api/integrations/discord/webhook/{integration_id}")
async def discord_webhook(integration_id: str, request: Request) -> dict[str, Any]:
    """Handle Discord interactions/events and route shared slash commands."""
    adapter = _get_channel_adapter("discord", integration_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    payload = await request.json()
    result = await adapter.handle_event(payload, dict(request.headers))
    owner_user_id = str(_get_channel_config("discord", integration_id).get("owner_user_id", "")).strip() or None

    selected_mode_raw = adapter.extract_mode_selection(payload if isinstance(payload, dict) else {})
    if selected_mode_raw:
        channel = str(payload.get("channel_id") or "").strip()
        if not owner_user_id:
            if channel:
                await _send_channel_text(
                    "discord",
                    integration_id,
                    channel,
                    "⚠️ Mode switching is only available for the owner session.",
                    log_source="mode_switch",
                )
            return _channel_webhook_response(result)
        runtime = _user_runtimes.get(owner_user_id)
        if not runtime:
            if channel:
                await _send_channel_text(
                    "discord",
                    integration_id,
                    channel,
                    "⚠️ No active session. Start a session first.",
                    log_source="mode_switch",
                )
            return _channel_webhook_response(result)
        selected_mode, mode_valid, mode_error = _apply_runtime_mode_update(runtime, selected_mode_raw)
        if not mode_valid:
            if channel:
                await _send_channel_text(
                    "discord",
                    integration_id,
                    channel,
                    f"❌ {mode_error}",
                    log_source="mode_switch",
                )
            return _channel_webhook_response(result)
        if channel:
            await _send_channel_text(
                "discord",
                integration_id,
                channel,
                f"✅ Mode switched to *{MODE_LABELS.get(selected_mode, selected_mode.title())}*",
                log_source="mode_switch",
            )
        return _channel_webhook_response(result)

    inbound = adapter.extract_message(payload if isinstance(payload, dict) else {})
    channel = inbound.destination
    text_content = inbound.text
    platform_message_id = inbound.message_id
    if channel and text_content and text_content.startswith("/"):
        cmd_response = await _handle_slash_command(
            text=text_content,
            owner_uid=owner_user_id,
            platform="discord",
            integration_id=integration_id,
            chat_id=channel,
        )
        if isinstance(cmd_response, dict):
            await _send_channel_text(
                "discord",
                integration_id,
                channel,
                str(cmd_response.get("text", "")),
                metadata=_build_channel_command_metadata("discord", cmd_response),
                log_source="slash_command",
            )
        elif cmd_response:
            await _send_channel_text(
                "discord",
                integration_id,
                channel,
                cmd_response,
                log_source="slash_command",
            )
        return _channel_webhook_response(result)

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
    return _channel_webhook_response(result)



@app.post("/api/integrations/discord/{integration_id}/test")
async def test_discord_integration(integration_id: str) -> dict[str, Any]:
    adapter = _get_channel_adapter("discord", integration_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    result = await adapter.test_connection()
    return {"ok": bool(result.get("ok")), "result": result}



@app.post("/api/integrations/discord/{integration_id}/send_message")
async def discord_send_message(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    channel = str(payload.get("channel", "")).strip()
    text = str(payload.get("text", "")).strip()
    if not channel:
        raise HTTPException(status_code=400, detail="Channel is required")
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    metadata: dict[str, Any] = {}
    if isinstance(payload.get("components"), list):
        metadata["components"] = payload["components"]
    result = await _send_channel_text(
        "discord",
        integration_id,
        channel,
        text,
        metadata=metadata,
        log_source="send_message",
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
        integration = _get_channel_integration("telegram", str(integration_id))
        if integration:
            await integration.send_photo(chat_id, image_b64)
    elif platform == "discord":
        integration = _get_channel_integration("discord", str(integration_id))
        if integration:
            await integration.execute_tool(
                "discord_send_image",
                {"channel": str(sub.get("channel_id", chat_id) or chat_id), "image_b64": image_b64},
            )


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
    if platform in {"telegram", "discord"}:
        await _send_channel_text(
            platform,
            integration_id,
            str(chat_id),
            reply,
            log_source="bot_runtime",
        )


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
            runtime.queued_instructions.enqueue(arg, lane="bot", source="slash_command", metadata={"command": "run"})
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
        runtime.queued_instructions.enqueue(arg, lane="bot", source="slash_command", metadata={"command": "queue"})
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
        integration = _get_channel_integration("telegram", integration_id)
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


async def _start_servers() -> None:
    """Start the primary FastAPI app on a single port."""
    import os as _os

    config_main = uvicorn.Config(app, host="0.0.0.0", port=int(_os.environ.get("PORT", settings.PORT)))
    server_main = uvicorn.Server(config_main)
    await server_main.serve()


if __name__ == "__main__":
    asyncio.run(_start_servers())
