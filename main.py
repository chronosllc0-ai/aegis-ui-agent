"""Aegis UI Navigator — FastAPI entrypoint."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/health")
async def health() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok", "version": "0.1.0"}


async def _send_step(websocket: WebSocket, step: dict[str, str | None]) -> None:
    """Send a step event over websocket."""
    await websocket.send_json({"type": "step", "data": step})


@app.websocket("/ws/navigate")
async def websocket_navigate(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time UI navigation sessions."""
    await websocket.accept()
    session_id = await live_manager.create_session()

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            callback: Callable[[dict[str, str | None]], Awaitable[None]] = lambda step: _send_step(websocket, step)

            if action == "navigate":
                result = await orchestrator.execute_task(
                    session_id=session_id,
                    instruction=str(data.get("instruction", "")),
                    on_step=callback,
                )
                await websocket.send_json({"type": "result", "data": result})
            elif action == "audio_chunk":
                transcript = await live_manager.process_audio(session_id, data.get("audio"))
                if transcript:
                    result = await orchestrator.execute_task(session_id=session_id, instruction=transcript, on_step=callback)
                    await websocket.send_json({"type": "result", "data": result})
            elif action == "stop":
                break
            else:
                await websocket.send_json({"type": "error", "data": {"message": f"Unknown action: {action}"}})
    except WebSocketDisconnect:
        logger.info("Websocket disconnected")
    finally:
        await live_manager.close_session(session_id)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
