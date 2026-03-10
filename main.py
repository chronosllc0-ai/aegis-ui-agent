"""FastAPI entrypoint exposing websocket navigation and integration management APIs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from config import settings
from integrations.base import IntegrationError
from integrations.manager import IntegrationManager
from orchestrator import AgentOrchestrator
from session import LiveSessionManager

logger = logging.getLogger(__name__)
FRONTEND_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"

orchestrator = AgentOrchestrator()
live_manager = LiveSessionManager()
integration_manager = IntegrationManager()

app = FastAPI(title="Aegis UI Navigator", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SessionRuntime:
    """Tracks per-websocket runtime state."""

    def __init__(self) -> None:
        self.current_task: asyncio.Task[None] | None = None
        self.task_running = False
        self.cancel_event = asyncio.Event()
        self.steering_context: list[str] = []
        self.queued_instructions: asyncio.Queue[str] = asyncio.Queue()
        self.settings: dict[str, Any] = {}


class NativeConnectRequest(BaseModel):
    user_id: str = "demo-user"
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)


class NativeExecuteRequest(BaseModel):
    user_id: str = "demo-user"
    tool_name: str
    params: dict[str, Any] = Field(default_factory=dict)


class NativeTestRequest(BaseModel):
    user_id: str = "demo-user"


class MCPConnectRequest(BaseModel):
    user_id: str = "demo-user"
    name: str
    transport: Literal["streamable_http", "sse", "stdio"]
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)


class MCPExecuteRequest(BaseModel):
    user_id: str = "demo-user"
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)


class MCPTestRequest(BaseModel):
    user_id: str = "demo-user"


@app.get("/health")
async def health() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/integrations")
async def list_integrations(user_id: str = "demo-user") -> dict[str, Any]:
    """List native integrations and custom MCP servers for user."""
    return {
        "native_integrations": integration_manager.list_native(user_id),
        "mcp_servers": integration_manager.list_mcp_servers(user_id),
    }


@app.post("/api/integrations/{kind}/connect")
async def connect_integration(kind: str, payload: NativeConnectRequest) -> dict[str, Any]:
    """Connect a native integration using config + secret payload."""
    try:
        return await integration_manager.connect_native(payload.user_id, kind, payload.config, payload.secrets)
    except IntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/integrations/{kind}/test")
async def test_integration(kind: str, payload: NativeTestRequest) -> dict[str, Any]:
    """Run integration health check."""
    try:
        return await integration_manager.test_native(payload.user_id, kind)
    except IntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/integrations/{kind}/execute")
async def execute_integration(kind: str, payload: NativeExecuteRequest) -> dict[str, Any]:
    """Execute integration tool call."""
    try:
        return await integration_manager.execute_native(payload.user_id, kind, payload.tool_name, payload.params)
    except IntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/integrations/{kind}")
async def disconnect_integration(kind: str, user_id: str = "demo-user") -> dict[str, Any]:
    """Disconnect native integration."""
    try:
        return await integration_manager.disconnect_native(user_id, kind)
    except IntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mcp/servers")
async def add_mcp_server(payload: MCPConnectRequest) -> dict[str, Any]:
    """Register and connect to custom MCP server."""
    try:
        return await integration_manager.add_mcp_server(payload.user_id, payload.name, payload.transport, payload.config, payload.secrets)
    except IntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/mcp/servers")
async def list_mcp_servers(user_id: str = "demo-user") -> dict[str, Any]:
    """List custom MCP servers."""
    return {"servers": integration_manager.list_mcp_servers(user_id)}


@app.delete("/api/mcp/servers/{server_id}")
async def delete_mcp_server(server_id: str, user_id: str = "demo-user") -> dict[str, Any]:
    """Delete MCP server registration."""
    return await integration_manager.delete_mcp_server(user_id, server_id)


@app.post("/api/mcp/servers/{server_id}/test")
async def test_mcp_server(server_id: str, payload: MCPTestRequest) -> dict[str, Any]:
    """Test MCP server and fetch discovered tools."""
    try:
        return await integration_manager.test_mcp_server(payload.user_id, server_id)
    except IntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mcp/servers/{server_id}/execute")
async def execute_mcp_server(server_id: str, payload: MCPExecuteRequest) -> dict[str, Any]:
    """Execute tool against a custom MCP server."""
    try:
        return await integration_manager.execute_mcp_server(payload.user_id, server_id, payload.tool_name, payload.args)
    except IntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/integrations/telegram/webhook/{integration_id}")
async def telegram_webhook(
    integration_id: str,
    payload: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    user_id: str = "demo-user",
) -> dict[str, Any]:
    """Receive Telegram webhook updates with optional secret token validation."""
    record = integration_manager.records.get(user_id, {}).get("telegram")
    if record is None:
        raise HTTPException(status_code=404, detail="Telegram integration not configured")
    expected = str(record.config.get("webhook_secret", ""))
    if expected and x_telegram_bot_api_secret_token != expected:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret token")
    return {"ok": True, "integration_id": integration_id, "update_id": payload.get("update_id")}


async def _send_step(websocket: WebSocket, step: dict[str, str | None]) -> None:
    """Send a step event over websocket."""
    await websocket.send_json({"type": "step", "data": step})


async def _send_frame(websocket: WebSocket, image_b64: str) -> None:
    """Send a base64 PNG frame over websocket."""
    await websocket.send_json({"type": "frame", "data": {"image": image_b64}})


async def _send_workflow_step(websocket: WebSocket, workflow_step: dict[str, Any]) -> None:
    """Send workflow graph step payload to frontend."""
    await websocket.send_json({"type": "workflow_step", "data": workflow_step})


async def _run_navigation_task(
    websocket: WebSocket,
    runtime: SessionRuntime,
    session_id: str,
    instruction: str,
) -> None:
    """Execute a navigation task and drain queued instructions afterwards."""
    callback: Callable[[dict[str, Any]], Awaitable[None]] = lambda step: _send_step(websocket, step)
    runtime.task_running = True
    runtime.cancel_event.clear()

    result = await orchestrator.execute_task(
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
    runtime.task_running = False

    while not runtime.queued_instructions.empty() and not runtime.task_running:
        queued_instruction = await runtime.queued_instructions.get()
        await _send_step(
            websocket,
            {
                "type": "queue",
                "content": f"Starting queued task: {queued_instruction}",
            },
        )
        runtime.current_task = asyncio.create_task(_run_navigation_task(websocket, runtime, session_id, queued_instruction))
        await runtime.current_task


@app.websocket("/ws/navigate")
async def websocket_navigate(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time UI navigation sessions."""
    await websocket.accept()
    session_id = await live_manager.create_session()
    runtime = SessionRuntime()

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            instruction = str(data.get("instruction", "")).strip()

            if action == "navigate":
                if runtime.task_running:
                    await websocket.send_json({"type": "error", "data": {"message": "Task already running"}})
                    continue
                runtime.current_task = asyncio.create_task(_run_navigation_task(websocket, runtime, session_id, instruction))
            elif action == "steer":
                runtime.steering_context.append(instruction)
                await _send_step(websocket, {"type": "steer", "content": f"Steering note added: {instruction}"})
            elif action == "interrupt":
                runtime.cancel_event.set()
                await _send_step(websocket, {"type": "interrupt", "content": "Task interrupted"})
                runtime.current_task = asyncio.create_task(_run_navigation_task(websocket, runtime, session_id, instruction))
            elif action == "queue":
                await runtime.queued_instructions.put(instruction)
                await _send_step(websocket, {"type": "queue", "content": f"Queued instruction: {instruction}"})
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
                    if runtime.task_running:
                        runtime.steering_context.append(transcript)
                    else:
                        runtime.current_task = asyncio.create_task(_run_navigation_task(websocket, runtime, session_id, transcript))
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


if FRONTEND_DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str) -> FileResponse:
        """Serve compiled frontend files in production."""
        candidate = FRONTEND_DIST_DIR / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
