"""Aegis UI Navigator - FastAPI entrypoint."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
import contextlib
from datetime import datetime, timedelta, timezone
import hashlib
from http.cookies import SimpleCookie
import json
import logging
from pathlib import Path
import re
import secrets
import time as _time
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, or_, select
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
from backend.connections.router import router as connections_router
from backend.connections.service import ensure_default_mcp_presets
from backend.integrations.channel_runtime import ChannelRuntimeRegistry, DiscordChannelAdapter, SlackChannelAdapter, TelegramChannelAdapter
from backend.integrations.text_normalization import normalize_for_channel
from backend.gallery.router import gallery_router
from backend.memory.router import memory_router
from backend.payments import payments_router
from backend.planner.executor_routes import executor_router
from backend.planner.router import planner_router
from backend.research.router import research_router
from backend.reasoning import (
    CANONICAL_REASONING_LEVELS,
    apply_reasoning_level,
    normalize_reasoning_level,
    reasoning_level_label,
    runtime_reasoning_level,
    runtime_reasoning_status,
)
from backend.skills.router import skills_router
from backend.skills_hub.router import skills_hub_router
from backend.skills.runtime import resolve_runtime_skills
from backend.tasks.router import task_router as tasks_router
from backend.workspace_files import legacy_workspace_files_router, workspace_files_router
from backend.workspace_files_service import (
    consume_session_bootstrap_file,
    load_session_workspace_file,
    materialize_workspace_files_for_session_safe,
)
from backend.tasks.worker import BackgroundWorker
from backend.session_gateway import SessionEventHub
from backend.session_lanes import QueuedInstruction, SessionLaneQueue
from backend.runtime_telemetry import RuntimeEventStore, RuntimeTelemetry
from backend.conversation_service import append_message, get_or_create_conversation
from backend.migration_rollout import (
    feature_flags_snapshot,
    legacy_conversation_mode_enabled,
    sessions_dual_write_enabled,
    sessions_v2_enabled,
)
from backend.session_store import append_session_message, get_or_create_session
from backend.sessions_migration_service import migrate_user_to_sessions_first
from backend.session_identity import (
    SESSION_MAIN_ID,
    normalize_or_bridge_session_id,
    session_id_to_conversation_id,
)
from backend.database import (
    IntegrationAccessPolicy,
    PairedChannelIdentity,
    PairingRequestAudit,
    SupportMessage,
    SupportThread,
    UserConnection,
    create_tables,
    get_session,
    init_db,
)
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
from backend.user_memory import ensure_daily_memory_file

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
app.include_router(connections_router)
app.include_router(gallery_router)
app.include_router(memory_router)
app.include_router(payments_router)
app.include_router(planner_router)
app.include_router(executor_router)
app.include_router(research_router)
app.include_router(tasks_router)
app.include_router(skills_router)
app.include_router(skills_hub_router)
app.include_router(workspace_files_router)
app.include_router(legacy_workspace_files_router)

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
            if database._session_factory is not None:
                async with database._session_factory() as session:
                    await ensure_default_mcp_presets(session)
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


class _LegacyRegistryView:
    """Backward-compatible platform registry view for older test scaffolding."""

    def __init__(self, platform: str) -> None:
        self.platform = platform

    class _StoreProxy:
        def __init__(self, platform: str) -> None:
            self.platform = platform

        def clear(self) -> None:
            prefix = f"{self.platform}:"
            stale_keys = [key for key in list(channel_registry._entries.keys()) if key.startswith(prefix)]
            for key in stale_keys:
                channel_registry._entries.pop(key, None)

    @property
    def _integrations(self) -> "_LegacyRegistryView._StoreProxy":
        return self._StoreProxy(self.platform)

    @property
    def _configs(self) -> "_LegacyRegistryView._StoreProxy":
        return self._StoreProxy(self.platform)

    def upsert(self, integration_id: str, integration: Any, config: dict[str, Any]) -> None:
        channel_registry.upsert(self.platform, integration_id, integration, config)

    def get_config(self, integration_id: str) -> dict[str, Any]:
        return channel_registry.get_config(self.platform, integration_id)


telegram_registry = _LegacyRegistryView("telegram")
slack_registry = _LegacyRegistryView("slack")
discord_registry = _LegacyRegistryView("discord")

# Maps authenticated user_uid -> active SessionRuntime (for bot command bridging)
_user_runtimes: dict[str, "SessionRuntime"] = {}
# Reverse index: session_id -> SessionRuntime for O(1) heartbeat dispatch
_session_runtimes: dict[str, "SessionRuntime"] = {}
runtime_telemetry = RuntimeTelemetry()
runtime_events = RuntimeEventStore(
    ttl_seconds=6 * 60 * 60,
    max_events=10000,
    persistence_path=Path("data/runtime_events.jsonl"),
)
session_migration_counters: dict[str, int] = {
    "send_total": 0,
    "send_mismatch": 0,
    "spawn_total": 0,
    "spawn_mismatch": 0,
}

_BROWSER_CHAT_POLLUTION_PREFIXES = (
    "[click",
    "[type_text",
    "[scroll",
    "[wait",
    "[go_to_url",
    "[go_back",
    "[screenshot",
    "[extract_page",
    "final synthesis:",
    "outcome:",
    "worker refs:",
)

_BROWSER_CHAT_POLLUTION_EXACT = {
    "task completed",
    "task completed.",
}

_BROWSER_CHAT_POLLUTION_SUMMARY_RE = re.compile(r"^(planner|architect|deep research|code|orchestrator) summary:", re.IGNORECASE)
_SYSTEM_CHAT_ACTION_DENYLIST = {
    "steer",
    "queue",
    "dequeue",
    "interrupt",
    "idle_steer_rejected",
    "idle_queue_rejected",
    "idle_interrupt_rejected",
    "heartbeat",
    "heartbeat_queue",
    "heartbeat_dispatch",
    "websocket_lifecycle",
    "mode_event",
    "mode_transition",
    "workflow_step",
    "task_state",
    "task_control",
}


def _is_browser_chat_pollution(step: dict[str, Any]) -> bool:
    """Return True when a step is execution-noise that should not be persisted to chat."""
    step_type = str(step.get("type") or "").strip().lower()
    if step_type in {"workflow_step", "browser_action", "human_browser_action"}:
        return True
    content = str(step.get("content") or "").strip()
    if not content:
        return False
    normalized = content.lower()
    if any(normalized.startswith(prefix) for prefix in _BROWSER_CHAT_POLLUTION_PREFIXES):
        return True
    if normalized in _BROWSER_CHAT_POLLUTION_EXACT:
        return True
    return bool(_BROWSER_CHAT_POLLUTION_SUMMARY_RE.match(content))


def _is_system_internal_chat_message(role: str, metadata: dict[str, Any] | None) -> bool:
    """Return True when a persisted chat row is internal/system-only noise."""
    if str(role or "").strip().lower() == "system":
        return True
    payload = metadata if isinstance(metadata, dict) else {}
    if payload.get("observability_only") is True or payload.get("user_visible") is False:
        return True
    source = str(payload.get("source") or "").strip().lower()
    action = str(payload.get("action") or "").strip().lower()
    if source in {"heartbeat", "runtime_internal", "mode_router"}:
        return True
    return action in _SYSTEM_CHAT_ACTION_DENYLIST


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
        "telemetry": runtime_telemetry.snapshot(),
        "routes": list(route_snapshots.values()),
    }


set_runtime_inspector(_runtime_snapshot)

def _record_runtime_event(
    *,
    category: str,
    subsystem: str,
    level: str,
    message: str,
    session_id: str | None = None,
    request_id: str | None = None,
    task_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Record an internal observability event without failing runtime flows."""
    try:
        runtime_events.append(
            category=category,
            subsystem=subsystem,
            level=level,
            message=message,
            session_id=session_id,
            request_id=request_id,
            task_id=task_id,
            details=details,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("runtime event capture failed: %s", exc)


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
    runtime_telemetry.record_channel_tool_result(platform, ok=bool(result.get("ok")))
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
    _record_runtime_event(
        category="heartbeat",
        subsystem="heartbeat",
        level="info",
        message="heartbeat trigger received",
        session_id=session_id,
        details={"instruction": instruction},
    )
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
        _record_runtime_event(
            category="heartbeat",
            subsystem="heartbeat",
            level="info",
            message="heartbeat instruction queued",
            session_id=session_id,
            request_id=runtime.current_request_id,
            task_id=runtime.current_task_id,
            details={"instruction": instruction},
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
    _record_runtime_event(
        category="heartbeat",
        subsystem="heartbeat",
        level="info",
        message="heartbeat instruction dispatch started",
        session_id=session_id,
        request_id=runtime.current_request_id,
        task_id=runtime.current_task_id,
        details={"instruction": instruction},
    )
    _start_navigation_task(runtime.websocket, runtime, session_id, instruction)


_pinger = HeartbeatPinger(dispatch=_heartbeat_dispatch, interval_seconds=60)
background_worker.set_event_sink(_dispatch_background_task_event)

# Stream subscribers: user_uid -> {platform, integration_id, chat_id, last_sent_at}
_stream_subscribers: dict[str, dict[str, Any]] = {}

# Bot config: integration_id -> config dict
_bot_configs: dict[str, dict[str, Any]] = {}
PAIRING_CODE_TTL_SECONDS = 600
PAIRING_CHALLENGE_RATE_LIMIT_SECONDS = 90
_pairing_challenge_last_issued_at: dict[str, float] = {}


def _get_effective_bot_config(platform: str, integration_id: str) -> dict[str, Any]:
    """Resolve runtime bot config from channel config + in-memory overrides."""
    channel_cfg = _get_channel_config(platform, integration_id)
    stored_bot_cfg = channel_cfg.get("bot_config") if isinstance(channel_cfg, dict) else None
    in_memory_cfg = _bot_configs.get(f"{platform}:{integration_id}", {})
    if isinstance(stored_bot_cfg, dict):
        return {**stored_bot_cfg, **in_memory_cfg}
    return dict(in_memory_cfg)


def _update_runtime_bot_config(platform: str, integration_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial bot-config patch into process state and channel runtime config."""
    key = f"{platform}:{integration_id}"
    current = _bot_configs.get(key, {})
    merged = {**current, **patch}
    _bot_configs[key] = merged

    entry = channel_registry.get_entry(platform, integration_id)
    if entry is not None:
        runtime_cfg = dict(entry.config)
        existing_runtime_bot_cfg = runtime_cfg.get("bot_config") if isinstance(runtime_cfg.get("bot_config"), dict) else {}
        runtime_cfg["bot_config"] = {**existing_runtime_bot_cfg, **patch}
        channel_registry.upsert(entry.platform, integration_id, entry.adapter, runtime_cfg)

    return merged


def _hash_pairing_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_pairing_code() -> str:
    return secrets.token_urlsafe(6).replace("-", "").replace("_", "").upper()[:8]


def _pairing_rate_limit_key(
    *,
    platform: str,
    integration_id: str,
    external_user_id: str,
    external_channel_id: str | None,
) -> str:
    channel_fragment = external_channel_id or "dm"
    return f"{platform}:{integration_id}:{external_user_id}:{channel_fragment}"


def _remaining_pairing_ttl_seconds(expires_at: datetime | None, *, now: datetime) -> int:
    if expires_at is None:
        return 0
    return max(0, int((expires_at.replace(tzinfo=timezone.utc) - now).total_seconds()))


def _build_pairing_challenge_text(*, reject_message: str, pairing_code: str) -> str:
    ttl_minutes = PAIRING_CODE_TTL_SECONDS // 60
    return (
        f"{reject_message}\n\n"
        "🔐 Pairing challenge:\n"
        f"Code: `{pairing_code}`\n"
        f"Use `/pair {pairing_code}` to complete pairing (expires in {ttl_minutes}m)."
    )


def _build_pairing_challenge_metadata(
    *,
    platform: str,
    request_id: str,
    nonce: str,
) -> dict[str, Any]:
    if platform != "telegram":
        return {}
    return {"parse_mode": "Markdown", "reply_markup": TelegramIntegration.pairing_challenge_reply_markup(request_id, nonce)}


def _parse_pairing_callback(update: dict[str, Any]) -> tuple[str, str, str] | None:
    callback_query = update.get("callback_query")
    if not isinstance(callback_query, dict):
        return None
    return TelegramIntegration.extract_pairing_callback(callback_query.get("data"))


async def _get_or_create_integration_policy(
    db: AsyncSession,
    *,
    platform: str,
    integration_id: str,
) -> IntegrationAccessPolicy:
    result = await db.execute(
        select(IntegrationAccessPolicy).where(
            and_(
                IntegrationAccessPolicy.platform == platform,
                IntegrationAccessPolicy.integration_id == integration_id,
            )
        )
    )
    policy = result.scalar_one_or_none()
    if policy is not None:
        return policy
    policy = IntegrationAccessPolicy(platform=platform, integration_id=integration_id)
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


async def _record_pairing_audit(
    db: AsyncSession,
    *,
    platform: str,
    integration_id: str,
    external_user_id: str,
    external_username: str | None,
    external_channel_id: str | None,
    chat_type: str | None,
    event_type: str,
    status: str,
    actor_user_id: str | None = None,
    pairing_code_hash: str | None = None,
    code_expires_at: datetime | None = None,
    code_used_at: datetime | None = None,
    notes: str | None = None,
) -> PairingRequestAudit:
    event = PairingRequestAudit(
        platform=platform,
        integration_id=integration_id,
        external_user_id=external_user_id,
        external_username=external_username,
        external_channel_id=external_channel_id,
        chat_type=chat_type,
        event_type=event_type,
        status=status,
        actor_user_id=actor_user_id,
        pairing_code_hash=pairing_code_hash,
        code_expires_at=code_expires_at,
        code_used_at=code_used_at,
        notes=notes,
    )
    db.add(event)
    await db.flush()
    return event


def _resolve_external_sender_identity(platform: str, payload: dict[str, Any]) -> dict[str, str | None]:
    if platform == "telegram":
        return TelegramIntegration.extract_sender_identity(payload)
    if platform == "slack":
        return SlackIntegration.extract_sender_identity(payload)
    if platform == "discord":
        return DiscordIntegration.extract_sender_identity(payload)
    return {"external_user_id": None, "external_username": None, "chat_type": None, "chat_id": None}


async def _try_consume_pairing_code(
    db: AsyncSession,
    *,
    platform: str,
    integration_id: str,
    external_user_id: str,
    external_username: str | None,
    external_channel_id: str | None,
    chat_type: str | None,
    pairing_code: str,
) -> bool:
    now = datetime.now(timezone.utc)
    code_hash = _hash_pairing_code(pairing_code.strip().upper())
    pending_result = await db.execute(
        select(PairingRequestAudit).where(
            and_(
                PairingRequestAudit.platform == platform,
                PairingRequestAudit.integration_id == integration_id,
                PairingRequestAudit.external_user_id == external_user_id,
                PairingRequestAudit.status == "pending",
                PairingRequestAudit.pairing_code_hash == code_hash,
            )
        )
    )
    pending = pending_result.scalar_one_or_none()
    if pending is None or pending.code_expires_at is None:
        return False
    if pending.code_expires_at.replace(tzinfo=timezone.utc) < now:
        pending.status = "expired"
        return False

    pending.status = "approved"
    pending.code_used_at = now
    pair_result = await db.execute(
        select(PairedChannelIdentity).where(
            and_(
                PairedChannelIdentity.platform == platform,
                PairedChannelIdentity.integration_id == integration_id,
                PairedChannelIdentity.external_user_id == external_user_id,
            )
        )
    )
    pair = pair_result.scalar_one_or_none()
    if pair is None:
        pair = PairedChannelIdentity(
            platform=platform,
            integration_id=integration_id,
            external_user_id=external_user_id,
            external_username=external_username,
            status="approved",
            metadata_json=json.dumps({"chat_id": external_channel_id, "chat_type": chat_type}),
        )
        db.add(pair)
    else:
        pair.status = "approved"
        pair.external_username = external_username or pair.external_username
        pair.last_seen_at = now
    await _record_pairing_audit(
        db,
        platform=platform,
        integration_id=integration_id,
        external_user_id=external_user_id,
        external_username=external_username,
        external_channel_id=external_channel_id,
        chat_type=chat_type,
        event_type="create",
        status="approved",
        actor_user_id=None,
        code_used_at=now,
        notes="Pairing code verified",
    )
    return True


async def _enforce_ingress_policy(
    *,
    platform: str,
    integration_id: str,
    payload: dict[str, Any],
    text_content: str | None,
) -> tuple[bool, str | None, dict[str, Any] | None]:
    external = _resolve_external_sender_identity(platform, payload)
    external_user_id = str(external.get("external_user_id") or "").strip()
    if not external_user_id:
        return False, None, None
    external_username = str(external.get("external_username") or "").strip() or None
    chat_type = str(external.get("chat_type") or "").strip().lower() or "group"
    external_channel_id = str(external.get("chat_id") or "").strip() or None
    session_id = str(external.get("session_id") or "").strip() or None

    def _blocked(
        message: str | None,
        *,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None, dict[str, Any] | None]:
        _record_runtime_event(
            category="ingress.blocked",
            subsystem="ingress",
            level="info",
            message=str(message or "Ingress blocked by policy."),
            session_id=session_id,
            details={
                "platform": platform,
                "integration_id": integration_id,
                "external_user_id": external_user_id,
                "external_channel_id": external_channel_id,
                "chat_type": chat_type,
                "status": status,
            },
        )
        return False, message, metadata

    session_iter = get_session()
    db = await anext(session_iter)
    try:
        policy = await _get_or_create_integration_policy(db, platform=platform, integration_id=integration_id)
        if chat_type == "dm" and not policy.allow_direct_messages:
            return _blocked("Direct messages are disabled for this integration.", status="policy_direct_messages_disabled")
        if chat_type != "dm" and not policy.allow_group_messages:
            return _blocked("Group messages are disabled for this integration.", status="policy_group_messages_disabled")

        bot_cfg = _get_effective_bot_config(platform, integration_id)
        dm_mode = str(bot_cfg.get("dm_policy_mode") or "allow_all").strip().lower()
        group_mode = str(bot_cfg.get("group_policy_mode") or "allow_all").strip().lower()
        dm_allow_from = {str(x).strip() for x in (bot_cfg.get("dm_allow_from") or []) if str(x).strip()}
        group_allow_from = {str(x).strip() for x in (bot_cfg.get("group_allow_from") or []) if str(x).strip()}

        if chat_type == "dm":
            if dm_mode == "deny_all":
                return _blocked("Direct messages are blocked by policy.", status="dm_deny_all")
            if dm_mode == "allowlist" and external_user_id not in dm_allow_from:
                return _blocked("You are not in the DM allowlist for this integration.", status="dm_allowlist_blocked")
        else:
            if group_mode == "deny_all":
                return _blocked("Group messages are blocked by policy.", status="group_deny_all")
            if group_mode == "allowlist":
                # OR semantics are intentional: entries may be either approved user IDs or approved channel IDs.
                allowlisted = external_user_id in group_allow_from or (external_channel_id is not None and external_channel_id in group_allow_from)
                if not allowlisted:
                    return _blocked("This group is not allowlisted for this integration.", status="group_allowlist_blocked")

        if not policy.pairing_required:
            return True, None, None

        pair_result = await db.execute(
            select(PairedChannelIdentity).where(
                and_(
                    PairedChannelIdentity.platform == platform,
                    PairedChannelIdentity.integration_id == integration_id,
                    PairedChannelIdentity.external_user_id == external_user_id,
                )
            )
        )
        pair = pair_result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if pair and pair.status == "approved":
            pair.last_seen_at = now
            await db.commit()
            return True, None, None

        pair_callback = _parse_pairing_callback(payload) if platform == "telegram" else None
        if pair_callback is not None:
            action, request_id, nonce = pair_callback
            pending_result = await db.execute(
                select(PairingRequestAudit).where(
                    and_(
                        PairingRequestAudit.id == request_id,
                        PairingRequestAudit.platform == platform,
                        PairingRequestAudit.integration_id == integration_id,
                        PairingRequestAudit.external_user_id == external_user_id,
                        PairingRequestAudit.status == "pending",
                        PairingRequestAudit.event_type == "request",
                    )
                )
            )
            pending = pending_result.scalar_one_or_none()
            if pending is None:
                return _blocked("⚠️ This pairing request is no longer active. Send /pair to request a new code.", status="pairing_request_missing")
            if pending.code_expires_at and pending.code_expires_at.replace(tzinfo=timezone.utc) < now:
                pending.status = "expired"
                await db.commit()
                return _blocked("⌛ Pairing code expired. Send /pair to request a new challenge.", status="pairing_code_expired")
            expected_nonce = pending.id[-8:]
            if nonce != expected_nonce:
                return _blocked("❌ Invalid pairing callback token. Send /pair for a new challenge.", status="pairing_callback_invalid")
            ttl_seconds = _remaining_pairing_ttl_seconds(pending.code_expires_at, now=now)
            if action == "help":
                return _blocked("Use `/pair <code>` in this DM to complete pairing.", status="pairing_help", metadata={"parse_mode": "Markdown"})
            return _blocked(f"⏳ Pending owner approval. Current code TTL: ~{max(1, ttl_seconds)}s.", status="pairing_pending")

        if text_content and text_content.lower().startswith("/pair "):
            parts = text_content.split(" ", 1)
            pairing_code = parts[1].strip() if len(parts) > 1 else ""
            if pairing_code and await _try_consume_pairing_code(
                db,
                platform=platform,
                integration_id=integration_id,
                external_user_id=external_user_id,
                external_username=external_username,
                external_channel_id=external_channel_id,
                chat_type=chat_type,
                pairing_code=pairing_code,
            ):
                await db.commit()
                _record_runtime_event(
                    category="pairing.approved",
                    subsystem="pairing",
                    level="info",
                    message="pairing approved via code challenge",
                    session_id=session_id,
                    details={
                        "platform": platform,
                        "integration_id": integration_id,
                        "external_user_id": external_user_id,
                        "external_channel_id": external_channel_id,
                        "status": "approved",
                    },
                )
                return False, "✅ Pairing complete. You can now run commands.", None
            code_hash = _hash_pairing_code(pairing_code.strip().upper()) if pairing_code else ""
            if code_hash:
                expired_match = await db.execute(
                    select(PairingRequestAudit).where(
                        and_(
                            PairingRequestAudit.platform == platform,
                            PairingRequestAudit.integration_id == integration_id,
                            PairingRequestAudit.external_user_id == external_user_id,
                            PairingRequestAudit.pairing_code_hash == code_hash,
                            PairingRequestAudit.event_type == "request",
                        )
                    )
                )
                expired_row = expired_match.scalar_one_or_none()
                if (
                    expired_row is not None
                    and expired_row.code_expires_at is not None
                    and expired_row.code_expires_at.replace(tzinfo=timezone.utc) < now
                ):
                    expired_row.status = "expired"
                    await db.commit()
                    return _blocked("⌛ Pairing code expired. Send /pair to request a new challenge.", status="pairing_code_expired")
            await db.commit()
            return _blocked("❌ Invalid or expired pairing code.", status="pairing_code_invalid")

        existing_pending = await db.execute(
            select(PairingRequestAudit).where(
                and_(
                    PairingRequestAudit.platform == platform,
                    PairingRequestAudit.integration_id == integration_id,
                    PairingRequestAudit.external_user_id == external_user_id,
                    PairingRequestAudit.status == "pending",
                    PairingRequestAudit.event_type == "request",
                )
            )
        )
        pending = existing_pending.scalar_one_or_none()
        if pending is not None and pending.code_expires_at and pending.code_expires_at.replace(tzinfo=timezone.utc) < now:
            pending.status = "expired"
            await db.commit()
            pending = None
        if text_content and text_content.strip().lower() == "/pair":
            if pending is not None:
                ttl_seconds = _remaining_pairing_ttl_seconds(pending.code_expires_at, now=now)
                return _blocked(f"⏳ Pairing challenge already issued. Expires in ~{max(1, ttl_seconds)}s.", status="pairing_already_issued")
            return _blocked("ℹ️ Use `/pair <code>` after receiving your pairing challenge.", status="pairing_usage_hint")
        if pending is None:
            rate_key = _pairing_rate_limit_key(
                platform=platform,
                integration_id=integration_id,
                external_user_id=external_user_id,
                external_channel_id=external_channel_id,
            )
            last_issued_at = _pairing_challenge_last_issued_at.get(rate_key, 0.0)
            now_ts = _time.time()
            elapsed = now_ts - last_issued_at
            if elapsed < PAIRING_CHALLENGE_RATE_LIMIT_SECONDS:
                wait_seconds = max(1, int(PAIRING_CHALLENGE_RATE_LIMIT_SECONDS - elapsed))
                return _blocked(f"⏱️ Please wait ~{wait_seconds}s before requesting another pairing code.", status="pairing_rate_limited")
            pairing_code = _generate_pairing_code()
            request_event = await _record_pairing_audit(
                db,
                platform=platform,
                integration_id=integration_id,
                external_user_id=external_user_id,
                external_username=external_username,
                external_channel_id=external_channel_id,
                chat_type=chat_type,
                event_type="request",
                status="pending",
                pairing_code_hash=_hash_pairing_code(pairing_code),
                code_expires_at=now + timedelta(seconds=PAIRING_CODE_TTL_SECONDS),
                notes="Pairing requested by external identity.",
            )
            _pairing_challenge_last_issued_at[rate_key] = now_ts
            await db.commit()
            _record_runtime_event(
                category="pairing.requested",
                subsystem="pairing",
                level="info",
                message="pairing challenge issued",
                session_id=session_id,
                details={
                    "platform": platform,
                    "integration_id": integration_id,
                    "external_user_id": external_user_id,
                    "external_channel_id": external_channel_id,
                    "status": "pending",
                    "request_id": request_event.id,
                },
            )
            challenge_text = _build_pairing_challenge_text(reject_message=policy.reject_message, pairing_code=pairing_code)
            challenge_metadata = _build_pairing_challenge_metadata(
                platform=platform,
                request_id=request_event.id,
                nonce=request_event.id[-8:],
            )
            return False, challenge_text, challenge_metadata
        ttl_seconds = _remaining_pairing_ttl_seconds(pending.code_expires_at, now=now)
        return _blocked(f"{policy.reject_message} Existing code expires in ~{max(1, ttl_seconds)}s.", status="pairing_pending_existing")
    finally:
        await session_iter.aclose()


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
        self.handoff_active: bool = False
        self.handoff_request_id: str | None = None
        self.handoff_future: asyncio.Future[str] | None = None
        self.handoff_started_at: float | None = None
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

    def clear_handoff_state(self) -> None:
        """Reset any active human handoff state."""
        self.handoff_active = False
        self.handoff_request_id = None
        self.handoff_future = None
        self.handoff_started_at = None

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
    apply_reasoning_level(merged, runtime_reasoning_level(merged))
    return merged


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


# ── Conversation persistence API ─────────────────────────────────────

@app.get("/api/conversations")
async def list_conversations(
    request: Request,
    limit: int = 50,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Legacy compatibility adapter that exposes session data as conversations."""
    user = _get_current_user(request)
    uid = user["uid"]
    await migrate_user_to_sessions_first(db, user_id=uid, platform="web")
    await db.commit()
    from sqlalchemy import select as sa_select, desc as sa_desc
    from backend.database import ChatSession as SessionModel
    stmt = (
        sa_select(SessionModel)
        .where(SessionModel.user_id == uid, SessionModel.platform == "web", SessionModel.status != "archived")
        .order_by(sa_desc(SessionModel.updated_at))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "ok": True,
        "conversations": [
            {
                "id": c.session_id,
                "title": c.title,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in rows
        ],
    }


@app.get("/api/sessions")
async def list_sessions(
    request: Request,
    limit: int = 50,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return chat sessions from v2 storage with legacy bridge fallback."""
    user = _get_current_user(request)
    uid = user["uid"]
    await migrate_user_to_sessions_first(db, user_id=uid, platform="web")
    await db.commit()
    from sqlalchemy import select as sa_select, desc as sa_desc
    from backend.database import ChatSession as SessionModel, Conversation as ConvModel
    rows: list[Any]
    if sessions_v2_enabled():
        stmt = (
            sa_select(SessionModel)
            .where(SessionModel.user_id == uid, SessionModel.platform == "web", SessionModel.status != "archived")
            .order_by(sa_desc(SessionModel.updated_at))
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return {
            "ok": True,
            "sessions": [
                {
                    "session_id": row.session_id,
                    "conversation_id": None,
                    "parent_session_id": row.parent_session_id,
                    "title": row.title,
                    "status": row.status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in rows
            ],
        }
    stmt = (
        sa_select(ConvModel)
        .where(ConvModel.user_id == uid, ConvModel.platform == "web", ConvModel.status != "archived")
        .order_by(sa_desc(ConvModel.updated_at))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "ok": True,
        "sessions": [
            {
                "session_id": normalize_or_bridge_session_id(
                    c.platform_chat_id or "",
                    fallback_conversation_id=c.id,
                ),
                "conversation_id": c.id,
                "parent_session_id": None,
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
    from backend.database import (
        ChatSession as SessionModel,
        ChatSessionMessage as SessionMsgModel,
        Conversation as ConvModel,
        ConversationMessage as MsgModel,
    )
    if sessions_v2_enabled():
        session_row = (
            await db.execute(
                sa_select(SessionModel).where(
                    SessionModel.user_id == uid,
                    SessionModel.platform == "web",
                    SessionModel.session_id == normalize_or_bridge_session_id(conversation_id),
                    SessionModel.status != "archived",
                )
            )
        ).scalar_one_or_none()
        if session_row:
            messages = (
                await db.execute(
                    sa_select(SessionMsgModel)
                    .where(SessionMsgModel.session_ref_id == session_row.id, SessionMsgModel.role != "system")
                    .order_by(SessionMsgModel.created_at)
                    .limit(limit)
                )
            ).scalars().all()
            return {
                "ok": True,
                "conversation": {
                    "id": session_row.session_id,
                    "title": session_row.title,
                    "created_at": session_row.created_at.isoformat() if session_row.created_at else None,
                },
                "messages": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "metadata": _json.loads(m.metadata_json) if m.metadata_json else None,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in messages
                ],
            }
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


@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    request: Request,
    limit: int = 500,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return session messages while excluding system events from chat transcript."""
    user = _get_current_user(request)
    uid = user["uid"]
    import json as _json
    from sqlalchemy import select as sa_select
    from backend.database import (
        ChatSession as SessionModel,
        ChatSessionMessage as SessionMsgModel,
        Conversation as ConvModel,
        ConversationMessage as MsgModel,
    )

    requested_session_id = normalize_or_bridge_session_id(session_id)
    if sessions_v2_enabled():
        session_row = (
            await db.execute(
                sa_select(SessionModel).where(
                    SessionModel.user_id == uid,
                    SessionModel.platform == "web",
                    SessionModel.session_id == requested_session_id,
                )
            )
        ).scalar_one_or_none()
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = (
            await db.execute(
                sa_select(SessionMsgModel)
                .where(SessionMsgModel.session_ref_id == session_row.id, SessionMsgModel.role != "system")
                .order_by(SessionMsgModel.created_at)
                .limit(limit)
            )
        ).scalars().all()
        return {
            "ok": True,
            "session": {
                "session_id": session_row.session_id,
                "conversation_id": None,
                "parent_session_id": session_row.parent_session_id,
                "title": session_row.title,
                "created_at": session_row.created_at.isoformat() if session_row.created_at else None,
            },
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "metadata": _json.loads(m.metadata_json) if m.metadata_json else None,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
        }

    bridged_conversation_id = session_id_to_conversation_id(requested_session_id)
    conv_stmt = sa_select(ConvModel).where(ConvModel.user_id == uid, ConvModel.platform == "web")
    if bridged_conversation_id:
        conv_stmt = conv_stmt.where(ConvModel.id == bridged_conversation_id)
    else:
        conv_stmt = conv_stmt.where(ConvModel.platform_chat_id == requested_session_id)
    conv = (await db.execute(conv_stmt)).scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = (
        sa_select(MsgModel)
        .where(MsgModel.conversation_id == conv.id)
        .order_by(MsgModel.created_at)
        .limit(limit)
    )
    msgs = (await db.execute(stmt)).scalars().all()
    resolved_session_id = normalize_or_bridge_session_id(conv.platform_chat_id or "", fallback_conversation_id=conv.id)
    return {
        "ok": True,
        "session": {
            "session_id": resolved_session_id,
            "conversation_id": conv.id,
            "parent_session_id": None,
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
            if m.role != "system"
        ],
    }


@app.post("/api/sessions/{session_id}/send")
async def send_session_message(
    session_id: str,
    request: Request,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Append a user message with sessions-v2 + dual-write migration safety."""
    user = _get_current_user(request)
    uid = user["uid"]
    content = str(payload.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    import json as _json
    from backend.database import ChatSession as SessionModel, Conversation as ConvModel, ConversationMessage as MsgModel
    from sqlalchemy import select as sa_select

    normalized_session_id = normalize_or_bridge_session_id(session_id)
    resolved_conversation_id: str | None = None
    if sessions_v2_enabled():
        session_row = (
            await db.execute(
                sa_select(SessionModel).where(
                    SessionModel.user_id == uid,
                    SessionModel.platform == "web",
                    SessionModel.session_id == normalized_session_id,
                )
            )
        ).scalar_one_or_none()
        if session_row is None:
            session_row = await get_or_create_session(
                db,
                user_id=uid,
                platform="web",
                session_id=normalized_session_id,
                title=(payload.get("title") or content[:80]).strip(),
            )
        await append_session_message(
            db,
            session_ref_id=session_row.id,
            role="user",
            content=content,
            metadata={"source": "sessions_api"},
        )

    if legacy_conversation_mode_enabled() or sessions_dual_write_enabled():
        bridged_conversation_id = session_id_to_conversation_id(normalized_session_id)
        conv_stmt = sa_select(ConvModel).where(ConvModel.user_id == uid, ConvModel.platform == "web")
        if bridged_conversation_id:
            conv_stmt = conv_stmt.where(ConvModel.id == bridged_conversation_id)
        else:
            conv_stmt = conv_stmt.where(ConvModel.platform_chat_id == normalized_session_id)
        conv = (await db.execute(conv_stmt)).scalar_one_or_none()
        if not conv:
            conv = ConvModel(
                user_id=uid,
                platform="web",
                platform_chat_id=normalized_session_id,
                title=(payload.get("title") or content[:80]).strip(),
                status="active",
            )
            db.add(conv)
            await db.flush()
        msg = MsgModel(
            conversation_id=conv.id,
            role="user",
            content=content,
            metadata_json=_json.dumps({"source": "sessions_api"}),
        )
        db.add(msg)
        resolved_conversation_id = conv.id
    else:
        msg = type("TmpMsg", (), {"id": None, "role": "user", "content": content, "created_at": None})()

    session_migration_counters["send_total"] = int(session_migration_counters["send_total"]) + 1
    if sessions_dual_write_enabled() and resolved_conversation_id is None:
        session_migration_counters["send_mismatch"] = int(session_migration_counters["send_mismatch"]) + 1

    from datetime import datetime as _dt
    if resolved_conversation_id:
        conv.updated_at = _dt.utcnow()
    await db.commit()
    if hasattr(msg, "__table__"):
        await db.refresh(msg)
    return {
        "ok": True,
        "session_id": normalized_session_id,
        "conversation_id": resolved_conversation_id,
        "message": {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        },
    }


@app.post("/api/sessions/spawn")
async def spawn_session(
    request: Request,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Spawn a sub-agent session entry with dual-write safeguards."""
    user = _get_current_user(request)
    uid = user["uid"]
    parent_session_id = str(payload.get("parent_session_id") or SESSION_MAIN_ID).strip() or SESSION_MAIN_ID
    instruction = str(payload.get("instruction") or "").strip()
    session_id = f"agent:main:subagent:spawn:task:{uuid4().hex}"
    title = str(payload.get("title") or instruction[:80] or "Subagent session").strip()
    from backend.database import Conversation as ConvModel

    if sessions_v2_enabled():
        session_row = await get_or_create_session(
            db,
            user_id=uid,
            platform="web",
            session_id=session_id,
            title=title,
            parent_session_id=parent_session_id,
        )
        await append_session_message(
            db,
            session_ref_id=session_row.id,
            role="assistant",
            content=f"Spawned subagent session from parent {parent_session_id}",
            metadata={"source": "session_spawn", "parent_session_id": parent_session_id, "instruction": instruction},
        )

    conversation_id: str | None = None
    if legacy_conversation_mode_enabled() or sessions_dual_write_enabled():
        conv = ConvModel(
            user_id=uid,
            platform="web",
            platform_chat_id=session_id,
            title=title,
            status="active",
        )
        db.add(conv)
        await db.flush()
        await append_message(
            db,
            conversation_id=conv.id,
            role="assistant",
            content=f"Spawned subagent session from parent {parent_session_id}",
            metadata={"source": "session_spawn", "parent_session_id": parent_session_id, "instruction": instruction},
        )
        conversation_id = conv.id

    session_migration_counters["spawn_total"] = int(session_migration_counters["spawn_total"]) + 1
    if sessions_dual_write_enabled() and conversation_id is None:
        session_migration_counters["spawn_mismatch"] = int(session_migration_counters["spawn_mismatch"]) + 1

    await db.commit()
    return {
        "ok": True,
        "session": {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "parent_session_id": parent_session_id,
            "title": title,
            "status": "active",
        },
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
    if runtime and session_id and not _is_browser_chat_pollution(normalized_step):
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
        page = getattr(executor, "page", None)
        current_url = getattr(page, "url", None) if page is not None else None
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
    # Workflow graph steps belong in action log, not user-facing chat history.


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
        _record_runtime_event(
            category="ws_ping_pong",
            subsystem="websocket",
            level="error",
            message="websocket send failed",
            session_id=ws_session_id,
            request_id=request_id,
            task_id=task_id,
            details={"phase": phase, "error": str(exc)},
        )
        return False


def _normalize_start_metadata(raw_metadata: object) -> dict[str, Any]:
    """Return a normalized metadata object without mutating inbound payloads."""
    if not isinstance(raw_metadata, dict):
        return {}
    allowed_keys = {
        "frontend_task_id",
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
    """Persist websocket messages with session-v2 dual-write and fallback support."""
    if not runtime.user_uid:
        return
    if _is_system_internal_chat_message(role, metadata):
        _record_runtime_event(
            category="chat_filter",
            subsystem="chat",
            level="debug",
            message="internal chat message dropped",
            session_id=session_id,
            request_id=runtime.current_request_id,
            task_id=runtime.current_task_id,
            details={
                "role": role,
                "source": str((metadata or {}).get("source") or ""),
                "action": str((metadata or {}).get("action") or ""),
            },
        )
        return
    try:
        async for db in get_session():
            wrote_session = False
            if sessions_v2_enabled():
                session_row = await get_or_create_session(
                    db,
                    user_id=runtime.user_uid,
                    platform="web",
                    session_id=session_id,
                    title=title or title_candidate,
                )
                await append_session_message(
                    db,
                    session_ref_id=session_row.id,
                    role=role,
                    content=content,
                    metadata=metadata,
                )
                wrote_session = True

            if legacy_conversation_mode_enabled() or sessions_dual_write_enabled():
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
            elif wrote_session:
                runtime.conversation_id = None
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
    """Handle idle control actions; steer auto-starts while queue/interrupt remain rejected."""
    if action == "steer":
        request_id = str(uuid4())
        task_id = str(uuid4())
        runtime.current_request_id = request_id
        runtime.current_task_id = task_id
        runtime.current_frontend_task_id = task_id
        _record_runtime_event(
            category="queue_steer_runtime",
            subsystem="runtime",
            level="info",
            message="idle steer auto-start accepted",
            session_id=session_id,
            request_id=request_id,
            task_id=task_id,
            details={"instruction": instruction, "task_label": task_label, "client": client_metadata or {}},
        )
        await _safe_ws_send(
            websocket,
            {"type": "navigate_ack", "data": {"request_id": request_id, "task_id": task_id, "accepted": True}},
            request_id=request_id,
            task_id=task_id,
            ws_session_id=session_id,
            phase="idle_steer_autostart_ack",
        )
        await _safe_ws_send(
            websocket,
            {"type": "task_state", "data": {"task_id": task_id, "state": "queued", "timestamp": _time.time()}},
            request_id=request_id,
            task_id=task_id,
            ws_session_id=session_id,
            phase="idle_steer_autostart_queued",
        )
        _start_navigation_task(websocket, runtime, session_id, instruction)
        return

    await websocket.send_json(
        {
            "type": "error",
            "data": {
                "message": f"{action}: no active task. Use navigate to start a new task.",
            },
        }
    )
    _record_runtime_event(
        category="queue_steer_runtime",
        subsystem="runtime",
        level="info",
        message=f"idle {action} rejected",
        session_id=session_id,
        request_id=runtime.current_request_id,
        task_id=runtime.current_task_id,
        details={"instruction": instruction, "task_label": task_label, "client": client_metadata or {}},
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
    first_emit_logged = False

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
        nonlocal first_emit_logged
        await _send_step(websocket, step, runtime=runtime, session_id=session_id)
        step_type = str(step.get("type") or "").lower()
        if not first_emit_logged:
            first_emit_logged = True
            logger.info(
                "navigation_trace request_id=%s task_id=%s ws_session_id=%s phase=first_step_emit step_type=%s",
                request_id,
                task_id,
                session_id,
                step_type or "unknown",
            )
        if step_type in {"tool_start", "tool_result", "tool-call", "tool_call"}:
            _record_runtime_event(
                category="tool_lifecycle",
                subsystem="tools",
                level="info",
                message=f"internal tool lifecycle: {step_type}",
                session_id=session_id,
                request_id=request_id,
                task_id=task_id,
                details={"step": step},
            )
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

    async def _on_handoff_to_user(
        reason: str,
        instructions: str,
        continue_label: str | None,
        request_id: str,
    ) -> str:
        """Pause execution and wait for user-triggered handoff_continue."""
        fut: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        runtime.handoff_active = True
        runtime.handoff_request_id = request_id
        runtime.handoff_future = fut
        runtime.handoff_started_at = _time.time()
        try:
            await websocket.send_json(
                {
                    "type": "step",
                    "data": {
                        "type": "handoff_request",
                        "content": f"[handoff_to_user] {reason}",
                        "request_id": request_id,
                        "reason": reason,
                        "instructions": instructions,
                        "continue_label": continue_label,
                    },
                }
            )
            timeout_candidate = runtime.settings.get("handoff_timeout_seconds") or settings.NAVIGATION_HANDOFF_TIMEOUT_SECONDS
            try:
                timeout_seconds = int(timeout_candidate)
            except (TypeError, ValueError):
                timeout_seconds = settings.NAVIGATION_HANDOFF_TIMEOUT_SECONDS
            return await asyncio.wait_for(fut, timeout=max(1, timeout_seconds))
        except asyncio.TimeoutError:
            runtime.clear_handoff_state()
            raise RuntimeError("Handoff timed out after waiting for manual completion.")
        finally:
            if runtime.handoff_future is fut and fut.done():
                runtime.clear_handoff_state()

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

    async def _on_first_model_call(model_name: str, provider_name: str) -> None:
        logger.info(
            "navigation_trace request_id=%s task_id=%s ws_session_id=%s phase=first_model_call provider=%s model=%s",
            request_id,
            task_id,
            session_id,
            provider_name,
            model_name,
        )
        _record_runtime_event(
            category="task_start",
            subsystem="orchestrator",
            level="info",
            message="first model call",
            session_id=session_id,
            request_id=request_id,
            task_id=task_id,
            details={"model": model_name, "provider": provider_name},
        )

    try:
        max_duration_seconds = int(runtime.settings.get("model_timeout_seconds") or settings.NAVIGATION_TASK_TIMEOUT_SECONDS)
        max_tool_calls = int(runtime.settings.get("max_tool_calls") or settings.NAVIGATION_MAX_TOOL_CALLS)
        effective_runtime_settings = {
            "max_tool_calls": max_tool_calls,
            "model_timeout_seconds": max_duration_seconds,
            **runtime.settings,
        }
        logger.info(
            "navigation_trace request_id=%s task_id=%s ws_session_id=%s phase=orchestrator_start",
            request_id,
            task_id,
            session_id,
        )
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
            on_handoff_to_user=_on_handoff_to_user,
            on_reasoning_delta=_on_reasoning_delta,
            on_spawn_subagent=_on_spawn_subagent,
            on_message_subagent=_on_message_subagent,
            on_first_model_call=_on_first_model_call,
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
                if not first_emit_logged:
                    first_emit_logged = True
                    logger.info(
                        "navigation_trace request_id=%s task_id=%s ws_session_id=%s phase=first_error_emit",
                        request_id,
                        task_id,
                        session_id,
                    )
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
        if not first_emit_logged:
            first_emit_logged = True
            logger.info(
                "navigation_trace request_id=%s task_id=%s ws_session_id=%s phase=first_result_emit",
                request_id,
                task_id,
                session_id,
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
        runtime.clear_handoff_state()
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
    _record_runtime_event(
        category="websocket_lifecycle",
        subsystem="websocket",
        level="info",
        message="websocket session opened",
        session_id=session_id,
        details={"user_uid": runtime.user_uid},
    )
    ensure_daily_memory_file(session_id)

    db_session_gen = get_session()
    try:
        db_session = await anext(db_session_gen)
        await materialize_workspace_files_for_session_safe(db_session, session_id, runtime.user_uid)
    except Exception:
        logger.exception("Workspace file sync failed during websocket session bootstrap")
    finally:
        await db_session_gen.aclose()

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
            raw_metadata = data.get("metadata")
            client_metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
            task_label = str(client_metadata.get("task_label", "")).strip()
            title_candidate = task_label or instruction

            if action == "navigate_start":
                request_id = str(data.get("request_id") or "").strip()
                client_request_id = str(data.get("client_request_id") or "").strip()
                if not request_id:
                    request_id = str(uuid4())
                logger.info(
                    "navigate_start_receive request_id=%s client_request_id=%s ws_session_id=%s action=%s",
                    request_id,
                    client_request_id,
                    session_id,
                    action,
                )
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
                    "navigate_start request_id=%s client_request_id=%s task_id=%s ws_session_id=%s phase=ack outcome=accepted",
                    request_id,
                    client_request_id,
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
                logger.info(
                    "navigate_start_dispatch request_id=%s client_request_id=%s task_id=%s ws_session_id=%s phase=task_start_call",
                    request_id,
                    client_request_id,
                    task_id,
                    session_id,
                )
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
                _record_runtime_event(
                    category="queue_steer_runtime",
                    subsystem="runtime",
                    level="info",
                    message="steer instruction accepted",
                    session_id=session_id,
                    request_id=runtime.current_request_id,
                    task_id=runtime.current_task_id,
                    details={"instruction": instruction, "source": "websocket"},
                )
                await _send_step(
                    websocket,
                    {"type": "steer", "content": f"Steering note added: {instruction}"},
                    runtime=runtime,
                    session_id=session_id,
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
                _record_runtime_event(
                    category="queue_steer_runtime",
                    subsystem="runtime",
                    level="info",
                    message="interrupt follow-up started",
                    session_id=session_id,
                    request_id=runtime.current_request_id,
                    task_id=runtime.current_task_id,
                    details={"instruction": instruction, "source": "websocket", "client": client_metadata or {}},
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
                _record_runtime_event(
                    category="queue_steer_runtime",
                    subsystem="runtime",
                    level="info",
                    message="instruction queued",
                    session_id=session_id,
                    request_id=runtime.current_request_id,
                    task_id=runtime.current_task_id,
                    details={"instruction": instruction, "lane": "interactive"},
                )
                await _send_step(
                    websocket,
                    {"type": "queue", "content": f"Queued instruction: {instruction}"},
                    runtime=runtime,
                    session_id=session_id,
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
                    _record_runtime_event(
                        category="queue_steer_runtime",
                        subsystem="runtime",
                        level="info",
                        message="queued instruction removed",
                        session_id=session_id,
                        request_id=runtime.current_request_id,
                        task_id=runtime.current_task_id,
                        details={"index": index, "instruction": removed.instruction, "lane": removed.lane},
                    )
                    await _send_step(
                        websocket,
                        {"type": "queue", "content": f"Removed queued instruction: {removed.instruction}"},
                        runtime=runtime,
                        session_id=session_id,
                    )
                else:
                    _record_runtime_event(
                        category="queue_steer_runtime",
                        subsystem="runtime",
                        level="warning",
                        message="dequeue rejected: invalid index",
                        session_id=session_id,
                        request_id=runtime.current_request_id,
                        task_id=runtime.current_task_id,
                        details={"index": raw_index},
                    )
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
            elif action == "handoff_continue":
                request_id = str(data.get("request_id") or "").strip()
                if not runtime.handoff_active:
                    await _safe_ws_send(
                        websocket,
                        {"type": "task_error", "data": {"task_id": runtime.current_task_id, "code": "E_BAD_PAYLOAD", "message": "handoff_continue: no active handoff", "retryable": False}},
                        request_id=runtime.current_request_id,
                        task_id=runtime.current_task_id,
                        ws_session_id=session_id,
                        phase="handoff_continue_idle",
                    )
                    continue
                if not request_id or request_id != runtime.handoff_request_id:
                    await _safe_ws_send(
                        websocket,
                        {"type": "task_error", "data": {"task_id": runtime.current_task_id, "code": "E_BAD_PAYLOAD", "message": "handoff_continue: request_id mismatch", "retryable": True}},
                        request_id=runtime.current_request_id,
                        task_id=runtime.current_task_id,
                        ws_session_id=session_id,
                        phase="handoff_continue_mismatch",
                    )
                    continue
                fut = runtime.handoff_future
                if fut and not fut.done():
                    fut.set_result("Human handoff completed. Resuming agent.")
                runtime.clear_handoff_state()
                await _send_step(
                    websocket,
                    {"type": "handoff_complete", "content": "Human handoff completed. Resuming agent."},
                    runtime=runtime,
                    session_id=session_id,
                )
            elif action == "human_browser_action":
                if not runtime.handoff_active:
                    await _safe_ws_send(
                        websocket,
                        {"type": "task_error", "data": {"task_id": runtime.current_task_id, "code": "E_BAD_PAYLOAD", "message": "human_browser_action: handoff is not active", "retryable": True}},
                        request_id=runtime.current_request_id,
                        task_id=runtime.current_task_id,
                        ws_session_id=session_id,
                        phase="human_browser_action_no_handoff",
                    )
                    continue
                action_kind = str(data.get("kind") or "").strip().lower()
                request_id = runtime.handoff_request_id or ""
                try:
                    if action_kind == "click":
                        x = int(data.get("x"))
                        y = int(data.get("y"))
                        if x < 0 or y < 0 or x > settings.VIEWPORT_WIDTH or y > settings.VIEWPORT_HEIGHT:
                            raise ValueError("click coordinates out of bounds")
                        await _get_orchestrator().executor.click(x, y)
                    elif action_kind == "type_text":
                        text = str(data.get("text") or "")
                        x_raw = data.get("x")
                        y_raw = data.get("y")
                        x = int(x_raw) if x_raw is not None else None
                        y = int(y_raw) if y_raw is not None else None
                        if x is not None and (x < 0 or x > settings.VIEWPORT_WIDTH):
                            raise ValueError("type_text x out of bounds")
                        if y is not None and (y < 0 or y > settings.VIEWPORT_HEIGHT):
                            raise ValueError("type_text y out of bounds")
                        await _get_orchestrator().executor.type_text(text, x, y)
                    elif action_kind == "scroll":
                        delta = int(data.get("deltaY"))
                        direction = "down" if delta > 0 else "up"
                        amount = min(max(abs(delta), 10), 1200)
                        await _get_orchestrator().executor.scroll(direction, amount)
                    elif action_kind == "press_key":
                        key = str(data.get("key") or "").strip()
                        if not key:
                            raise ValueError("press_key requires key")
                        await _get_orchestrator().executor.press_key(key)
                    else:
                        raise ValueError("unknown human browser action")
                except Exception as exc:  # noqa: BLE001
                    await _safe_ws_send(
                        websocket,
                        {"type": "task_error", "data": {"task_id": runtime.current_task_id, "code": "E_BAD_PAYLOAD", "message": f"human_browser_action rejected: {exc}", "retryable": True}},
                        request_id=runtime.current_request_id,
                        task_id=runtime.current_task_id,
                        ws_session_id=session_id,
                        phase="human_browser_action_invalid",
                    )
                    continue
                logger.info(
                    "hitl_action session_id=%s request_id=%s kind=%s payload=%s",
                    session_id,
                    request_id,
                    action_kind,
                    {k: data.get(k) for k in ("x", "y", "text", "key", "deltaY")},
                )
            elif action == "ping":
                _record_runtime_event(
                    category="ws_ping_pong",
                    subsystem="websocket",
                    level="debug",
                    message="ws ping received",
                    session_id=session_id,
                )
                await _safe_ws_send(websocket, {"type": "pong"}, ws_session_id=session_id, phase="pong")
                _record_runtime_event(
                    category="ws_ping_pong",
                    subsystem="websocket",
                    level="debug",
                    message="ws pong sent",
                    session_id=session_id,
                )
            elif action == "spawn_subagent":
                # ── Spawn a sub-agent ──────────────────────────────────
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
            elif action in {"message_subagent", "steer_subagent"}:
                # ── Steer a running sub-agent ──────────────────────────
                sub_id = str(data.get("sub_id", "")).strip()
                sub_message = str(data.get("message", "")).strip()
                priority = str(data.get("priority", "")).strip()
                if not sub_id or not sub_message:
                    await websocket.send_json({"type": "error", "data": {"message": f"{action}: sub_id and message are required"}})
                    continue
                steering_payload = _build_subagent_steering_payload(sub_message, priority=priority)
                ok = await runtime.subagent_manager.send_message(sub_id, steering_payload)
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
        _record_runtime_event(
            category="websocket_lifecycle",
            subsystem="websocket",
            level="info",
            message="websocket disconnected",
            session_id=session_id,
            request_id=runtime.current_request_id,
            task_id=runtime.current_task_id,
        )
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
        _record_runtime_event(
            category="websocket_lifecycle",
            subsystem="websocket",
            level="info",
            message="websocket session closed",
            session_id=session_id,
            request_id=runtime.current_request_id,
            task_id=runtime.current_task_id,
        )


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
    """Persist a platform message with session-v2 dual-write compatibility."""
    if not user_id:
        return
    session_iter = get_session()
    db = await anext(session_iter)
    try:
        normalized_session_id = normalize_or_bridge_session_id(str(platform_chat_id))
        if sessions_v2_enabled():
            session_row = await get_or_create_session(
                db,
                user_id=user_id,
                platform=platform,
                session_id=normalized_session_id,
                title=title,
            )
            await append_session_message(
                db,
                session_ref_id=session_row.id,
                role=role,
                content=content,
                metadata=metadata or {},
            )
        if legacy_conversation_mode_enabled() or sessions_dual_write_enabled():
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

    callback_reasoning_raw = adapter.extract_reasoning_selection(update)
    if callback_reasoning_raw is not None:
        callback_query = update.get("callback_query", {})
        callback_message = callback_query.get("message", {}) if isinstance(callback_query, dict) else {}
        callback_chat_id = (callback_message.get("chat") or {}).get("id")
        callback_message_id = callback_message.get("message_id")
        callback_destination = str(callback_chat_id) if callback_chat_id is not None else None
        if not owner_user_id:
            if callback_destination:
                await _send_channel_text(
                    "telegram",
                    integration_id,
                    callback_destination,
                    "⚠️ Reasoning controls are only available for the owner session.",
                    log_source="reasoning_switch",
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
                    log_source="reasoning_switch",
                )
            return _channel_webhook_response(result)
        level = normalize_reasoning_level(callback_reasoning_raw, fallback="medium")
        apply_reasoning_level(runtime.settings, level)
        if callback_destination and isinstance(callback_message_id, int):
            integration_client = _get_channel_integration("telegram", integration_id)
            if isinstance(integration_client, TelegramIntegration):
                await integration_client.execute_tool(
                    "telegram_edit_message",
                    {
                        "chat_id": int(callback_chat_id) if isinstance(callback_chat_id, int) else callback_chat_id,
                        "message_id": callback_message_id,
                        "text": f"✅ Reasoning set to *{reasoning_level_label(level)}*",
                        "parse_mode": "Markdown",
                    },
                )
        return _channel_webhook_response(result)

    inbound = adapter.extract_message(update)
    chat_id = inbound.destination
    text_content = inbound.text
    platform_message_id = inbound.message_id
    allowed, reject_message, reject_metadata = await _enforce_ingress_policy(
        platform="telegram",
        integration_id=integration_id,
        payload=update if isinstance(update, dict) else {},
        text_content=text_content,
    )
    if not allowed:
        if chat_id and reject_message:
            await _send_channel_text(
                "telegram",
                integration_id,
                chat_id,
                reject_message,
                metadata=reject_metadata,
                log_source="pairing_policy",
            )
        return _channel_webhook_response(result)

    if chat_id and text_content and text_content.startswith("/"):
        bot_cfg = _get_effective_bot_config('telegram', integration_id)
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
            source_message_id=platform_message_id,
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
        "signing_secret": str(payload.get("signing_secret", "")).strip(),
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
    integration = _get_channel_integration("slack", integration_id)
    if adapter is None or not isinstance(integration, SlackIntegration):
        raise HTTPException(status_code=404, detail="Integration not found")
    raw_body = await request.body()
    if not integration.verify_request_signature(raw_body, dict(request.headers)):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")
    content_type = str(request.headers.get("content-type") or "").lower()
    try:
        if "application/x-www-form-urlencoded" in content_type:
            form_data = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
            interaction_payload = form_data.get("payload", [None])[0]
            if interaction_payload:
                payload = json.loads(interaction_payload)
            else:
                payload = {key: values[0] if values else "" for key, values in form_data.items()}
        else:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Slack payload") from exc
    result = await adapter.handle_event(payload, dict(request.headers))
    owner_user_id = str(_get_channel_config("slack", integration_id).get("owner_user_id", "")).strip() or None

    slack_command = str(payload.get("command") or "").strip().lower()
    if slack_command in {"/reason", "/reasoning"}:
        channel = str(payload.get("channel_id") or "").strip()
        command_text = f"/reasoning {str(payload.get('text') or '').strip()}".strip()
        cmd_response = await _handle_slash_command(
            text=command_text,
            owner_uid=owner_user_id,
            platform="slack",
            integration_id=integration_id,
            chat_id=channel,
        )
        if channel and isinstance(cmd_response, dict):
            await _send_channel_text(
                "slack",
                integration_id,
                channel,
                str(cmd_response.get("text", "")),
                metadata=_build_channel_command_metadata("slack", cmd_response),
                log_source="slash_command",
            )
        elif channel and cmd_response:
            await _send_channel_text(
                "slack",
                integration_id,
                channel,
                cmd_response,
                log_source="slash_command",
            )
        return _channel_webhook_response(result)

    selected_reasoning_raw = adapter.extract_reasoning_selection(payload if isinstance(payload, dict) else {})
    if selected_reasoning_raw:
        channel = str(payload.get("channel", {}).get("id") or payload.get("channel_id") or "").strip()
        if not owner_user_id:
            if channel:
                await _send_channel_text(
                    "slack",
                    integration_id,
                    channel,
                    "⚠️ Reasoning controls are only available for the owner session.",
                    log_source="reasoning_switch",
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
                    log_source="reasoning_switch",
                )
            return _channel_webhook_response(result)
        level = normalize_reasoning_level(selected_reasoning_raw, fallback="medium")
        apply_reasoning_level(runtime.settings, level)
        if channel:
            await _send_channel_text(
                "slack",
                integration_id,
                channel,
                f"Reasoning set to {reasoning_level_label(level)}",
                log_source="reasoning_switch",
            )
        return _channel_webhook_response(result)

    inbound = adapter.extract_message(payload if isinstance(payload, dict) else {})
    channel = inbound.destination
    text_content = inbound.text
    platform_message_id = inbound.message_id
    allowed, reject_message, _reject_metadata = await _enforce_ingress_policy(
        platform="slack",
        integration_id=integration_id,
        payload=payload if isinstance(payload, dict) else {},
        text_content=text_content,
    )
    if not allowed:
        if channel and reject_message:
            await _send_channel_text("slack", integration_id, channel, reject_message, log_source="pairing_policy")
        return _channel_webhook_response(result)
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
        "public_key": str(payload.get("public_key", "")).strip(),
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
    integration = _get_channel_integration("discord", integration_id)
    if adapter is None or not isinstance(integration, DiscordIntegration):
        raise HTTPException(status_code=404, detail="Integration not found")
    raw_body = await request.body()
    if not integration.verify_interaction_signature(raw_body, dict(request.headers)):
        raise HTTPException(status_code=403, detail="Invalid Discord signature")
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Discord payload") from exc
    result = await adapter.handle_event(payload, dict(request.headers))
    if isinstance(result.get("response"), dict) and int(result["response"].get("type", 0) or 0) == 1:
        return _channel_webhook_response(result)
    owner_user_id = str(_get_channel_config("discord", integration_id).get("owner_user_id", "")).strip() or None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    command_name = str(data.get("name") or "").strip().lower()
    if command_name == "reasoning":
        channel = str(payload.get("channel_id") or "").strip()
        options = data.get("options") if isinstance(data.get("options"), list) else []
        effort = ""
        for option in options:
            if not isinstance(option, dict):
                continue
            if str(option.get("name") or "").strip().lower() == "effort":
                effort = str(option.get("value") or "").strip()
                break
        command_text = f"/reasoning {effort}".strip()
        cmd_response = await _handle_slash_command(
            text=command_text,
            owner_uid=owner_user_id,
            platform="discord",
            integration_id=integration_id,
            chat_id=channel,
        )
        if channel and isinstance(cmd_response, dict):
            await _send_channel_text(
                "discord",
                integration_id,
                channel,
                str(cmd_response.get("text", "")),
                metadata=_build_channel_command_metadata("discord", cmd_response),
                log_source="slash_command",
            )
        elif channel and cmd_response:
            await _send_channel_text(
                "discord",
                integration_id,
                channel,
                cmd_response,
                log_source="slash_command",
            )
        return _channel_webhook_response(result)

    selected_reasoning_raw = adapter.extract_reasoning_selection(payload if isinstance(payload, dict) else {})
    if selected_reasoning_raw:
        channel = str(payload.get("channel_id") or "").strip()
        if not owner_user_id:
            if channel:
                await _send_channel_text(
                    "discord",
                    integration_id,
                    channel,
                    "⚠️ Reasoning controls are only available for the owner session.",
                    log_source="reasoning_switch",
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
                    log_source="reasoning_switch",
                )
            return _channel_webhook_response(result)
        level = normalize_reasoning_level(selected_reasoning_raw, fallback="medium")
        apply_reasoning_level(runtime.settings, level)
        if channel:
            await _send_channel_text(
                "discord",
                integration_id,
                channel,
                f"Reasoning set to {reasoning_level_label(level)}",
                log_source="reasoning_switch",
            )
        return _channel_webhook_response(result)

    inbound = adapter.extract_message(payload if isinstance(payload, dict) else {})
    channel = inbound.destination
    text_content = inbound.text
    platform_message_id = inbound.message_id
    allowed, reject_message, _reject_metadata = await _enforce_ingress_policy(
        platform="discord",
        integration_id=integration_id,
        payload=payload if isinstance(payload, dict) else {},
        text_content=text_content,
    )
    if not allowed:
        if channel and reject_message:
            await _send_channel_text("discord", integration_id, channel, reject_message, log_source="pairing_policy")
        return _channel_webhook_response(result)
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


@app.get("/api/observability/events")
async def list_observability_events(
    request: Request,
    session_id: str | None = Query(default=None),
    subsystem: str | None = Query(default=None),
    level: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    integration: str | None = Query(default=None),
    user: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List internal observability events with retention and pagination metadata."""
    _get_current_user(request)
    if not feature_flags_snapshot()["observability_event_log"]:
        raise HTTPException(status_code=503, detail="observability_event_log flag disabled")
    return runtime_events.list_events(
        session_id=session_id,
        subsystem=subsystem,
        level=level,
        platform=platform,
        integration=integration,
        user=user,
        status=status,
        limit=limit,
        cursor=cursor,
    )


@app.get("/api/migration/validation")
async def migration_validation_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return migration mismatch counters for conversation-vs-session dual-write validation."""
    _get_current_user(request)
    from sqlalchemy import func
    from backend.database import ChatSession, ChatSessionMessage, Conversation, ConversationMessage

    conv_count = (
        await db.execute(select(func.count()).select_from(Conversation).where(Conversation.platform == "web", Conversation.status != "archived"))
    ).scalar_one()
    session_count = (
        await db.execute(
            select(func.count()).select_from(ChatSession).where(ChatSession.platform == "web", ChatSession.status != "archived")
        )
    ).scalar_one()
    conv_msg_count = (
        await db.execute(
            select(func.count())
            .select_from(ConversationMessage)
            .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
            .where(Conversation.platform == "web", Conversation.status != "archived")
        )
    ).scalar_one()
    session_msg_count = (
        await db.execute(
            select(func.count())
            .select_from(ChatSessionMessage)
            .join(ChatSession, ChatSession.id == ChatSessionMessage.session_ref_id)
            .where(ChatSession.platform == "web", ChatSession.status != "archived")
        )
    ).scalar_one()
    store_mismatch_count = abs(int(conv_count) - int(session_count)) + abs(int(conv_msg_count) - int(session_msg_count))
    return {
        "ok": True,
        "feature_flags": feature_flags_snapshot(),
        "rollback_enabled": legacy_conversation_mode_enabled(),
        "mismatch_counters": {
            "api_send_mismatch": int(session_migration_counters["send_mismatch"]),
            "api_spawn_mismatch": int(session_migration_counters["spawn_mismatch"]),
            "store_mismatch_count": store_mismatch_count,
            "conversation_count": int(conv_count),
            "session_count": int(session_count),
            "conversation_message_count": int(conv_msg_count),
            "session_message_count": int(session_msg_count),
        },
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
    {"command": "reason", "description": "Legacy reasoning controls"},
    {"command": "reasoning", "description": "Reasoning controls (alias of /reason)"},
    {"command": "model", "description": "Show current model"},
    {"command": "mode", "description": "Show or switch agent mode"},
    {"command": "activation", "description": "Show activation/session details"},
    {"command": "config", "description": "Show runtime config summary"},
    {"command": "acp", "description": "Agent control protocol: /acp spawn <task>"},
    {"command": "spawn", "description": "Spawn task (alias for /run)"},
    {"command": "pair", "description": "Pairing status for channel runtime"},
    {"command": "backup", "description": "Backup status"},
    {"command": "models", "description": "List models and switch"},
    {"command": "stream", "description": "Live browser screenshots: /stream start|stop"},
    {"command": "subagent", "description": "Sub-agent controls: /subagent steer <id> <message>"},
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
    typing_pulse_task: asyncio.Task[None] | None = None
    if platform == "telegram":
        integration = _get_channel_integration("telegram", str(integration_id))
        if isinstance(integration, TelegramIntegration) and integration.client:
            async def _typing_pulse() -> None:
                while runtime.task_running and not runtime.cancel_event.is_set():
                    try:
                        await integration.client.send_chat_action(chat_id, "typing")
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("telegram typing pulse failed: %s", exc)
                    await asyncio.sleep(4.5)

            typing_pulse_task = asyncio.create_task(_typing_pulse())
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
        if typing_pulse_task:
            typing_pulse_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await typing_pulse_task
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


async def _maybe_send_telegram_running_ack(
    *,
    runtime: "SessionRuntime" | None,
    platform: str,
    integration_id: str,
    chat_id: Any,
    source_message_id: str | None,
    ack_reaction: str,
) -> None:
    """Send lightweight in-flight acknowledgement for Telegram while task is running."""
    if platform != "telegram" or not runtime or not runtime.task_running:
        return
    integration = _get_channel_integration("telegram", integration_id)
    if not isinstance(integration, TelegramIntegration) or not integration.client:
        return
    if source_message_id and source_message_id.isdigit():
        try:
            await integration.execute_tool(
                "telegram_react",
                {
                    "chat_id": int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id,
                    "message_id": int(source_message_id),
                    "reaction": ack_reaction or "👀",
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("telegram ack reaction failed: %s", exc)
    try:
        await integration.client.send_chat_action(chat_id, "typing")
    except Exception as exc:  # noqa: BLE001
        logger.debug("telegram processing indicator failed: %s", exc)


async def _run_or_queue_from_bot_command(
    *,
    runtime: "SessionRuntime" | None,
    owner_uid: str | None,
    platform: str,
    integration_id: str,
    chat_id: Any,
    instruction: str,
    source_command: str,
) -> str:
    """Run immediately or queue a bot task command depending on runtime state."""
    if not instruction:
        usage = "/run <instruction>" if source_command == "run" else f"/{source_command} <instruction>"
        if source_command == "acp_spawn":
            usage = "/acp spawn <instruction>"
        return f"Usage: {usage}"
    if not runtime:
        return "⚪ No active session. Open the Aegis app first."
    if runtime.task_running:
        runtime.queued_instructions.enqueue(
            instruction,
            lane="bot",
            source="slash_command",
            metadata={"command": source_command},
        )
        return f"📋 Task queued (agent is busy): {instruction[:80]}"
    asyncio.create_task(
        _run_navigation_task_from_bot(
            runtime,
            str(owner_uid),
            platform,
            integration_id,
            chat_id,
            instruction,
        )
    )
    return f"🚀 Starting task: {instruction[:80]}"


def _build_subagent_steering_payload(message: str, priority: str | None = None) -> str:
    """Build a normalized sub-agent steering payload, optionally with priority annotation."""
    normalized_message = message.strip()
    normalized_priority = (priority or "").strip().lower()
    if normalized_priority in {"low", "normal", "high", "urgent"}:
        return f"[priority:{normalized_priority}] {normalized_message}"
    return normalized_message


REASONING_LABELS: dict[str, str] = {
    level: reasoning_level_label(level) for level in CANONICAL_REASONING_LEVELS
}


def _reasoning_status_text(runtime: "SessionRuntime") -> str:
    """Render canonical reasoning status text for channel responses."""
    status = runtime_reasoning_status(runtime.settings)
    enabled = "enabled" if status["enabled"] else "disabled"
    stream = "on" if status["stream_reasoning"] else "off"
    return f"🧠 Reasoning: *{enabled}* | Effort: {status['label']} | Stream: {stream}"


def _build_reasoning_selector_response(platform: str, runtime: "SessionRuntime") -> dict[str, Any]:
    """Build platform-specific reasoning selector UI response payload."""
    status = runtime_reasoning_status(runtime.settings)
    response: dict[str, Any] = {"text": _reasoning_status_text(runtime)}
    if platform == "telegram":
        response["reply_markup"] = TelegramIntegration.reasoning_selector_reply_markup(REASONING_LABELS)
    elif platform == "slack":
        response["blocks"] = SlackIntegration.reasoning_selector_blocks(
            current_level_label=status["label"],
            reasoning_labels=REASONING_LABELS,
        )
    elif platform == "discord":
        response["components"] = DiscordIntegration.reasoning_selector_components(REASONING_LABELS)
    return response


async def _handle_slash_command(
    text: str,
    owner_uid: str | None,
    platform: str,
    integration_id: str,
    chat_id: Any,
    ack_reaction: str = "",
    source_message_id: str | None = None,
) -> str | dict[str, Any] | None:
    """Parse a slash command and execute the appropriate action. Returns a reply string or None."""
    parts = text.strip().split(None, 1)
    cmd = parts[0].lstrip("/").lower().split("@")[0]  # strip bot username suffix
    arg = parts[1].strip() if len(parts) > 1 else ""

    runtime = _user_runtimes.get(owner_uid) if owner_uid else None
    await _maybe_send_telegram_running_ack(
        runtime=runtime,
        platform=platform,
        integration_id=integration_id,
        chat_id=chat_id,
        source_message_id=source_message_id,
        ack_reaction=ack_reaction,
    )

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
            "/reasoning [none|minimal|low|medium|high|xhigh|status] — reasoning mode\n"
            "/reason ... — legacy alias of /reasoning\n"
            "/activation — active session details\n"
            "/config — runtime config summary\n"
            "/acp spawn <instruction> — ACP task start\n"
            "/spawn <instruction> — alias for /run\n"
            "/subagent steer <id> <message> — steer a running sub-agent\n"
            "/pair — pairing status\n"
            "/backup — backup status\n"
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
        reasoning_status = runtime_reasoning_status(runtime.settings)
        reasoning_enabled = "enabled" if reasoning_status["enabled"] else "disabled"
        return (
            f"{state}\n🧠 Model: {model} ({provider})\n"
            f"🧠 Reasoning: {reasoning_enabled}\n⚙️ Effort: {reasoning_status['label']}\n📋 Queued: {queued}{credits_info}"
        )

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
        return await _run_or_queue_from_bot_command(
            runtime=runtime,
            owner_uid=owner_uid,
            platform=platform,
            integration_id=integration_id,
            chat_id=chat_id,
            instruction=arg,
            source_command="run",
        )

    if cmd == "spawn":
        return await _run_or_queue_from_bot_command(
            runtime=runtime,
            owner_uid=owner_uid,
            platform=platform,
            integration_id=integration_id,
            chat_id=chat_id,
            instruction=arg,
            source_command="spawn",
        )

    if cmd == "acp":
        if not arg:
            return "Usage: /acp spawn <instruction>"
        acp_parts = arg.split(None, 1)
        subcommand = acp_parts[0].lower()
        if subcommand != "spawn":
            return "Usage: /acp spawn <instruction>"
        instruction = acp_parts[1].strip() if len(acp_parts) > 1 else ""
        return await _run_or_queue_from_bot_command(
            runtime=runtime,
            owner_uid=owner_uid,
            platform=platform,
            integration_id=integration_id,
            chat_id=chat_id,
            instruction=instruction,
            source_command="acp_spawn",
        )

    if cmd == "steer":
        if not arg:
            return "Usage: /steer <guidance>"
        if not runtime:
            return "⚪ No active session."
        runtime.steering_context.append(arg)
        return f"🎯 Steering note added: {arg[:80]}"

    if cmd == "subagent":
        if not runtime:
            return "⚪ No active session."
        if not arg:
            return "Usage: /subagent steer <id> <message>"
        parts3 = arg.split(None, 2)
        if len(parts3) < 3 or parts3[0].lower() != "steer":
            return "Usage: /subagent steer <id> <message>"
        sub_id = parts3[1].strip()
        sub_message = parts3[2].strip()
        if not sub_id or not sub_message:
            return "Usage: /subagent steer <id> <message>"
        ok = await runtime.subagent_manager.send_message(sub_id, _build_subagent_steering_payload(sub_message))
        if not ok:
            return f"⚠️ Sub-agent {sub_id} not found or not running."
        return f"🎯 Sub-agent {sub_id} steering sent."

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

    if cmd in {"reason", "reasoning"}:
        sub = arg.lower().strip()
        if not runtime:
            return "⚪ No active session."
        if not sub:
            return _build_reasoning_selector_response(platform, runtime)
        if sub == "status":
            return _reasoning_status_text(runtime)
        if sub == "stream":
            apply_reasoning_level(runtime.settings, runtime_reasoning_level(runtime.settings))
            if runtime_reasoning_level(runtime.settings) == "none":
                apply_reasoning_level(runtime.settings, "medium")
            runtime.settings["stream_reasoning"] = True
            return f"🧠 Reasoning stream enabled. Effort: *{reasoning_level_label(runtime_reasoning_level(runtime.settings))}*."
        try:
            level = normalize_reasoning_level(sub)
        except ValueError:
            return (
                "Usage: /reasoning [none|minimal|low|medium|high|xhigh|status]\n"
                "Legacy aliases: /reason on|off|true|false|1|0|stream|status"
            )
        apply_reasoning_level(runtime.settings, level)
        return f"🧠 Reasoning set to *{reasoning_level_label(level)}*."

    if cmd == "activation":
        if not runtime:
            return "⚪ No active session."
        return (
            f"🧩 Activation: {'running' if runtime.task_running else 'ready'}\n"
            f"Session: `{runtime.session_id}`\n"
            f"Conversation: `{runtime.conversation_id or 'n/a'}`"
        )

    if cmd == "config":
        if not runtime:
            return "⚪ No active session."
        return (
            "⚙️ Runtime config\n"
            f"- provider: `{runtime.settings.get('provider', '')}`\n"
            f"- model: `{runtime.settings.get('model', '')}`\n"
            f"- reasoning: `{'on' if runtime_reasoning_level(runtime.settings) != 'none' else 'off'}`\n"
            f"- reasoning_effort: `{runtime_reasoning_status(runtime.settings)['label']}`"
        )

    if cmd == "pair":
        if not runtime:
            return "⚪ No active session to pair."
        return "🔗 Pairing is active for this connected owner session."

    if cmd == "backup":
        return "💾 Backup command is acknowledged. Full backup workflows are not wired in this channel yet."

    return f"❓ Unknown command: /{cmd}\nType /help for a list of commands."


def _assert_integration_owner(request: Request, platform: str, integration_id: str) -> str:
    user = _get_current_user(request)
    owner_uid = str(_get_channel_config(platform, integration_id).get("owner_user_id", "")).strip()
    if not owner_uid:
        raise HTTPException(status_code=404, detail="Integration owner not configured")
    if owner_uid != user["uid"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    return owner_uid


async def _post_pairing_approval_effects(
    *,
    platform: str,
    integration_id: str,
    owner_uid: str,
    external_channel_id: str | None,
) -> None:
    """Notify paired identity and wake owner runtime/event stream."""
    session_id = f"bot_{owner_uid}"
    runtime = _user_runtimes.get(owner_uid)
    if runtime is None:
        runtime = SessionRuntime()
        runtime.user_uid = owner_uid
        runtime.session_id = session_id
        runtime.settings = _merge_runtime_settings(runtime.settings, {})
        _user_runtimes[owner_uid] = runtime
        _session_runtimes[session_id] = runtime
    _record_runtime_event(
        category="pairing.approved",
        subsystem="pairing",
        level="info",
        message="pairing approved; owner runtime wake requested",
        session_id=session_id,
        details={
            "platform": platform,
            "integration_id": integration_id,
            "external_channel_id": external_channel_id,
            "owner_uid": owner_uid,
        },
    )
    try:
        session_iter = get_session()
        db_session = await anext(session_iter)
        try:
            await materialize_workspace_files_for_session_safe(db_session, session_id, owner_uid)
        finally:
            await session_iter.aclose()
    except Exception:  # noqa: BLE001
        logger.exception("Pairing approval workspace materialize failed for owner=%s session=%s", owner_uid, session_id)
    agents_content = load_session_workspace_file(session_id, "AGENTS.md")
    bootstrap_content = load_session_workspace_file(session_id, "BOOTSTRAP.md")
    if agents_content is not None or bootstrap_content is not None:
        _record_runtime_event(
            category="bootstrap_loaded",
            subsystem="workspace",
            level="info",
            message="workspace bootstrap files loaded",
            session_id=session_id,
            details={
                "owner_uid": owner_uid,
                "agents_loaded": agents_content is not None,
                "bootstrap_loaded": bootstrap_content is not None,
                "agents_bytes": len(agents_content or ""),
                "bootstrap_bytes": len(bootstrap_content or ""),
            },
        )
    if bootstrap_content is not None:
        consumed_path = consume_session_bootstrap_file(session_id)
        if consumed_path is not None:
            _record_runtime_event(
                category="bootstrap_consumed",
                subsystem="workspace",
                level="info",
                message="workspace bootstrap consumed and archived",
                session_id=session_id,
                details={
                    "owner_uid": owner_uid,
                    "archived_path": str(consumed_path),
                    "archived_name": consumed_path.name,
                },
            )
    if external_channel_id:
        try:
            await _send_channel_text(
                platform,
                integration_id,
                external_channel_id,
                "✅ Pairing approved by owner. You can now run commands.",
                log_source="pairing_approval",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("pairing approval confirmation send failed: %s", exc)
    try:
        await session_events.publish_to_user(
            owner_uid,
            {
                "type": "pairing_approved",
                "platform": platform,
                "integration_id": integration_id,
                "external_channel_id": external_channel_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            lane="system",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("pairing approval wake event failed: %s", exc)


@app.get("/api/integrations/{platform}/{integration_id}/pairing/pending")
async def get_pending_pairing_requests(
    platform: str,
    integration_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _assert_integration_owner(request, platform, integration_id)
    now = datetime.now(timezone.utc)
    rows = await session.execute(
        select(PairingRequestAudit).where(
            and_(
                PairingRequestAudit.platform == platform,
                PairingRequestAudit.integration_id == integration_id,
                PairingRequestAudit.status == "pending",
                PairingRequestAudit.event_type == "request",
                or_(
                    PairingRequestAudit.code_expires_at.is_(None),
                    PairingRequestAudit.code_expires_at >= now,
                ),
            )
        )
    )
    pending: list[dict[str, Any]] = []
    for row in rows.scalars().all():
        pending.append(
            {
                "request_id": row.id,
                "external_user_id": row.external_user_id,
                "external_username": row.external_username,
                "chat_type": row.chat_type,
                "external_channel_id": row.external_channel_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "code_expires_at": row.code_expires_at.isoformat() if row.code_expires_at else None,
            }
        )
    return {"ok": True, "pending": pending}


@app.post("/api/integrations/{platform}/{integration_id}/pairing/{request_id}/approve")
async def approve_pairing_request(
    platform: str,
    integration_id: str,
    request_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor_user_id = _assert_integration_owner(request, platform, integration_id)
    result = await session.execute(
        select(PairingRequestAudit).where(
            and_(
                PairingRequestAudit.id == request_id,
                PairingRequestAudit.platform == platform,
                PairingRequestAudit.integration_id == integration_id,
            )
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Pairing request not found")
    row.status = "approved"
    row.actor_user_id = actor_user_id
    row.code_used_at = datetime.now(timezone.utc)
    identity_result = await session.execute(
        select(PairedChannelIdentity).where(
            and_(
                PairedChannelIdentity.platform == platform,
                PairedChannelIdentity.integration_id == integration_id,
                PairedChannelIdentity.external_user_id == row.external_user_id,
            )
        )
    )
    identity = identity_result.scalar_one_or_none()
    if identity is None:
        identity = PairedChannelIdentity(
            platform=platform,
            integration_id=integration_id,
            external_user_id=row.external_user_id,
            external_username=row.external_username,
            status="approved",
            paired_by_user_id=actor_user_id,
            metadata_json=json.dumps({"chat_type": row.chat_type, "chat_id": row.external_channel_id}),
        )
        session.add(identity)
        await _record_pairing_audit(
            session,
            platform=platform,
            integration_id=integration_id,
            external_user_id=row.external_user_id,
            external_username=row.external_username,
            external_channel_id=row.external_channel_id,
            chat_type=row.chat_type,
            event_type="create",
            status="approved",
            actor_user_id=actor_user_id,
            notes="Created approved pair during admin approval",
        )
    else:
        identity.status = "approved"
        identity.external_username = row.external_username or identity.external_username
        identity.paired_by_user_id = actor_user_id
    await _record_pairing_audit(
        session,
        platform=platform,
        integration_id=integration_id,
        external_user_id=row.external_user_id,
        external_username=row.external_username,
        external_channel_id=row.external_channel_id,
        chat_type=row.chat_type,
        event_type="approve",
        status="approved",
        actor_user_id=actor_user_id,
        notes=f"Approved request {request_id}",
    )
    _record_runtime_event(
        category="pairing.approved",
        subsystem="pairing",
        level="info",
        message="pairing request approved by owner",
        details={
            "platform": platform,
            "integration_id": integration_id,
            "external_user_id": row.external_user_id,
            "external_channel_id": row.external_channel_id,
            "actor_user_id": actor_user_id,
            "status": "approved",
            "request_id": request_id,
        },
    )
    await session.commit()
    owner_uid = str(_get_channel_config(platform, integration_id).get("owner_user_id", "")).strip()
    if owner_uid:
        await _post_pairing_approval_effects(
            platform=platform,
            integration_id=integration_id,
            owner_uid=owner_uid,
            external_channel_id=row.external_channel_id,
        )
    return {"ok": True, "request_id": request_id, "status": "approved"}


@app.post("/api/integrations/{platform}/{integration_id}/pairing/{request_id}/deny")
async def deny_pairing_request(
    platform: str,
    integration_id: str,
    request_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor_user_id = _assert_integration_owner(request, platform, integration_id)
    result = await session.execute(
        select(PairingRequestAudit).where(
            and_(
                PairingRequestAudit.id == request_id,
                PairingRequestAudit.platform == platform,
                PairingRequestAudit.integration_id == integration_id,
            )
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Pairing request not found")
    row.status = "denied"
    row.actor_user_id = actor_user_id
    identity_result = await session.execute(
        select(PairedChannelIdentity).where(
            and_(
                PairedChannelIdentity.platform == platform,
                PairedChannelIdentity.integration_id == integration_id,
                PairedChannelIdentity.external_user_id == row.external_user_id,
            )
        )
    )
    identity = identity_result.scalar_one_or_none()
    if identity is not None and identity.status == "approved":
        identity.status = "revoked"
        await _record_pairing_audit(
            session,
            platform=platform,
            integration_id=integration_id,
            external_user_id=row.external_user_id,
            external_username=row.external_username,
            external_channel_id=row.external_channel_id,
            chat_type=row.chat_type,
            event_type="revoke",
            status="revoked",
            actor_user_id=actor_user_id,
            notes=f"Revoked previously approved identity while denying {request_id}",
        )
        _record_runtime_event(
            category="pairing.revoked",
            subsystem="pairing",
            level="warning",
            message="approved pairing identity revoked during denial",
            details={
                "platform": platform,
                "integration_id": integration_id,
                "external_user_id": row.external_user_id,
                "external_channel_id": row.external_channel_id,
                "actor_user_id": actor_user_id,
                "status": "revoked",
                "request_id": request_id,
            },
        )
    elif identity is None:
        session.add(
            PairedChannelIdentity(
                platform=platform,
                integration_id=integration_id,
                external_user_id=row.external_user_id,
                external_username=row.external_username,
                status="denied",
                paired_by_user_id=actor_user_id,
            )
        )
    else:
        identity.status = "denied"
    await _record_pairing_audit(
        session,
        platform=platform,
        integration_id=integration_id,
        external_user_id=row.external_user_id,
        external_username=row.external_username,
        external_channel_id=row.external_channel_id,
        chat_type=row.chat_type,
        event_type="deny",
        status="denied",
        actor_user_id=actor_user_id,
        notes=f"Denied request {request_id}",
    )
    _record_runtime_event(
        category="pairing.denied",
        subsystem="pairing",
        level="info",
        message="pairing request denied by owner",
        details={
            "platform": platform,
            "integration_id": integration_id,
            "external_user_id": row.external_user_id,
            "external_channel_id": row.external_channel_id,
            "actor_user_id": actor_user_id,
            "status": "denied",
            "request_id": request_id,
        },
    )
    await session.commit()
    return {"ok": True, "request_id": request_id, "status": "denied"}


@app.get("/api/integrations/{platform}/{integration_id}/policy")
async def get_integration_policy(
    platform: str,
    integration_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _assert_integration_owner(request, platform, integration_id)
    policy = await _get_or_create_integration_policy(session, platform=platform, integration_id=integration_id)
    return {
        "ok": True,
        "policy": {
            "pairing_required": bool(policy.pairing_required),
            "allow_direct_messages": bool(policy.allow_direct_messages),
            "allow_group_messages": bool(policy.allow_group_messages),
            "reject_message": policy.reject_message,
            "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
        },
    }


@app.put("/api/integrations/{platform}/{integration_id}/policy")
async def update_integration_policy(
    platform: str,
    integration_id: str,
    payload: dict[str, Any],
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor_user_id = _assert_integration_owner(request, platform, integration_id)
    policy = await _get_or_create_integration_policy(session, platform=platform, integration_id=integration_id)
    if "pairing_required" in payload:
        policy.pairing_required = bool(payload.get("pairing_required"))
    if "allow_direct_messages" in payload:
        policy.allow_direct_messages = bool(payload.get("allow_direct_messages"))
    if "allow_group_messages" in payload:
        policy.allow_group_messages = bool(payload.get("allow_group_messages"))
    if "reject_message" in payload:
        policy.reject_message = str(payload.get("reject_message") or policy.reject_message).strip() or policy.reject_message
    policy.updated_by_user_id = actor_user_id
    _record_runtime_event(
        category="policy.updated",
        subsystem="policy",
        level="info",
        message="integration ingress policy updated",
        details={
            "platform": platform,
            "integration_id": integration_id,
            "actor_user_id": actor_user_id,
            "status": "updated",
            "pairing_required": bool(policy.pairing_required),
            "allow_direct_messages": bool(policy.allow_direct_messages),
            "allow_group_messages": bool(policy.allow_group_messages),
        },
    )
    await session.commit()
    return {"ok": True}


# ── Bot config endpoints ─────────────────────────────────────────────


@app.get("/api/integrations/{platform}/config/{integration_id}")
async def get_bot_config(platform: str, integration_id: str, request: Request) -> dict[str, Any]:
    _get_current_user(request)  # auth check
    cfg = _get_effective_bot_config(platform, integration_id)
    return {"ok": True, "config": cfg}


@app.post("/api/integrations/{platform}/config/{integration_id}")
async def save_bot_config(platform: str, integration_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    _get_current_user(request)
    merged = _update_runtime_bot_config(platform, integration_id, payload)
    # Auto-register Telegram slash commands if token available
    if platform == "telegram":
        integration = _get_channel_integration("telegram", integration_id)
        if integration and merged.get("slash_commands_enabled", True):
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
