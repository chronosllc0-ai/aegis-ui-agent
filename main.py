"""Aegis UI Navigator — FastAPI entrypoint."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from aegis_logging import setup_logging
from orchestrator import AgentOrchestrator
from session import LiveSessionManager

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

app = FastAPI(title="Aegis UI Navigator", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = AgentOrchestrator()
live_manager = LiveSessionManager()

FRONTEND_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"


class SessionRuntime:
    """In-memory runtime state for a websocket navigation session."""

    def __init__(self) -> None:
        self.task_running = False
        self.current_task: asyncio.Task[None] | None = None
        self.cancel_event = asyncio.Event()
        self.steering_context: list[str] = []
        self.queued_instructions: asyncio.Queue[str] = asyncio.Queue()
        self.settings: dict[str, Any] = {}


@app.get("/health")
async def health() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok", "version": "0.1.0"}


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
                runtime.settings = data.get("settings", {})
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
