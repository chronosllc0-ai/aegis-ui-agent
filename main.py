"""Aegis UI Navigator — FastAPI entrypoint."""
import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.agent.orchestrator import AgentOrchestrator
from src.live.session import LiveSessionManager
from src.utils.config import settings
from src.utils.logging import setup_logging

app = FastAPI(title="Aegis UI Navigator", version="0.1.0")
setup_logging()

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
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.websocket("/ws/navigate")
async def websocket_navigate(websocket: WebSocket):
    """WebSocket endpoint for real-time UI navigation sessions."""
    await websocket.accept()
    session_id = await live_manager.create_session()

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "navigate":
                instruction = data.get("instruction", "")
                result = await orchestrator.execute_task(
                    session_id=session_id,
                    instruction=instruction,
                    on_step=lambda step: asyncio.create_task(
                        websocket.send_json({"type": "step", "data": step})
                    ),
                )
                await websocket.send_json({"type": "result", "data": result})

            elif action == "audio_chunk":
                # Forward audio to Live API for voice interaction
                audio_data = data.get("audio")
                transcript = await live_manager.process_audio(session_id, audio_data)
                if transcript:
                    result = await orchestrator.execute_task(
                        session_id=session_id,
                        instruction=transcript,
                        on_step=lambda step: asyncio.create_task(
                            websocket.send_json({"type": "step", "data": step})
                        ),
                    )
                    await websocket.send_json({"type": "result", "data": result})

            elif action == "stop":
                break

    except WebSocketDisconnect:
        pass
    finally:
        await live_manager.close_session(session_id)


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8080, reload=True)
