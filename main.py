"""Aegis UI Navigator — FastAPI entrypoint."""

from __future__ import annotations

import asyncio
<<<<<<< ours
import base64
=======
>>>>>>> theirs
from collections.abc import Awaitable, Callable
import logging
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from aegis_logging import setup_logging
from integrations.telegram import TelegramConfig, TelegramIntegration
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

orchestrator: AgentOrchestrator | None = None
live_manager = LiveSessionManager()

FRONTEND_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"


<<<<<<< ours
class TelegramRegistry:
    """In-memory telegram integration registry for webhook routing."""

    def __init__(self) -> None:
        self._integrations: dict[str, TelegramIntegration] = {}

    def get_telegram(self, integration_id: str) -> TelegramIntegration | None:
        return self._integrations.get(integration_id)

    def upsert(self, integration_id: str, integration: TelegramIntegration) -> None:
        self._integrations[integration_id] = integration


telegram_registry = TelegramRegistry()
=======
def _get_orchestrator() -> AgentOrchestrator:
    """Return a lazily initialized orchestrator instance."""
    global orchestrator
    if orchestrator is None:
        orchestrator = AgentOrchestrator()
    return orchestrator
>>>>>>> theirs


class SessionRuntime:
    """In-memory runtime state for a websocket navigation session."""

    def __init__(self) -> None:
        self.task_running = False
        self.current_task: asyncio.Task[None] | None = None
        self.cancel_event = asyncio.Event()
        self.steering_context: list[str] = []
<<<<<<< ours
        self.queued_instructions: asyncio.Queue[str] = asyncio.Queue()
        self.settings: dict[str, Any] = {}
=======
        self.queued_instructions: list[str] = []
>>>>>>> theirs


@app.get("/health")
async def health() -> dict[str, str]:
    """Return service health status."""
    return {"status": "ok", "version": "0.1.0"}


async def _send_screenshot(websocket: WebSocket) -> None:
    """Capture and send a fresh screenshot payload with URL and title."""
    try:
        screenshot_bytes = await orchestrator.executor.screenshot()
        page = orchestrator.executor.page
        title = ""
        url = ""
        if page is not None:
            url = page.url
            try:
                title = await page.title()
            except Exception:  # noqa: BLE001
                title = ""
        await websocket.send_json(
            {
                "type": "screenshot",
                "data": base64.b64encode(screenshot_bytes).decode("utf-8"),
                "url": url,
                "title": title,
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Screenshot capture failed: %s", exc)


async def _send_step_and_screenshot(websocket: WebSocket, step: dict[str, Any]) -> None:
    """Send step payload and immediately follow with a screenshot frame."""
    await websocket.send_json({"type": "step", "data": step})
    await _send_screenshot(websocket)


async def _send_workflow_step(websocket: WebSocket, workflow_step: dict[str, Any]) -> None:
    """Send workflow graph step payload to frontend."""
    await websocket.send_json({"type": "workflow_step", "data": workflow_step})


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
    callback: Callable[[dict[str, Any]], Awaitable[None]] = lambda step: _send_step_and_screenshot(websocket, step)
    runtime.task_running = True
    runtime.cancel_event.clear()

    result = await orchestrator.execute_task(
        session_id=session_id,
        instruction=instruction,
        on_step=callback,
        cancel_event=runtime.cancel_event,
        steering_context=runtime.steering_context,
        settings=runtime.settings,
        on_workflow_step=lambda step: _send_workflow_step(websocket, step),
    )
    await websocket.send_json({"type": "result", "data": result})
    runtime.task_running = False

    while not runtime.queued_instructions.empty() and not runtime.task_running:
        queued_instruction = await runtime.queued_instructions.get()
        await _send_step_and_screenshot(
            websocket,
            {
                "type": "queue",
                "content": f"Starting queued task: {queued_instruction}",
            },
        )
        runtime.current_task = asyncio.create_task(_run_navigation_task(websocket, runtime, session_id, queued_instruction))
        await runtime.current_task


async def _send_frame(websocket: WebSocket, image_b64: str) -> None:
    """Send a base64 PNG frame over websocket."""
    await websocket.send_json({"type": "frame", "data": {"image": image_b64}})


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
        result = await orchestrator.execute_task(
            session_id=session_id,
            instruction=instruction,
            on_step=callback,
            on_frame=lambda image_b64: _send_frame(websocket, image_b64),
            cancel_event=runtime.cancel_event,
            steering_context=runtime.steering_context,
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


async def _send_frame(websocket: WebSocket, image_b64: str) -> None:
    """Send a base64 PNG frame over websocket."""
    await websocket.send_json({"type": "frame", "data": {"image": image_b64}})


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
        result = await orchestrator.execute_task(
            session_id=session_id,
            instruction=instruction,
            on_step=callback,
            on_frame=lambda image_b64: _send_frame(websocket, image_b64),
            cancel_event=runtime.cancel_event,
            steering_context=runtime.steering_context,
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


async def _send_frame(websocket: WebSocket, image_b64: str) -> None:
    """Send a base64 PNG frame over websocket."""
    await websocket.send_json({"type": "frame", "data": {"image": image_b64}})


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


async def _send_frame(websocket: WebSocket, image_b64: str) -> None:
    """Send a base64 PNG frame over websocket."""
    await websocket.send_json({"type": "frame", "data": {"image": image_b64}})


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


@app.websocket("/ws/navigate")
async def websocket_navigate(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time UI navigation sessions."""
    await websocket.accept()
    session_id = await live_manager.create_session()
    runtime = SessionRuntime()

    try:
        await orchestrator.executor.ensure_browser()
        await _send_screenshot(websocket)

        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            instruction = str(data.get("instruction", "")).strip()

            if action == "navigate":
                if runtime.task_running:
                    await websocket.send_json({"type": "error", "data": {"message": "Task already running"}})
                    continue
<<<<<<< ours
                runtime.current_task = asyncio.create_task(_run_navigation_task(websocket, runtime, session_id, instruction))
            elif action == "steer":
                runtime.steering_context.append(instruction)
                await _send_step_and_screenshot(websocket, {"type": "steer", "content": f"Steering note added: {instruction}"})
            elif action == "interrupt":
                runtime.cancel_event.set()
                await _send_step_and_screenshot(websocket, {"type": "interrupt", "content": "Task interrupted"})
                runtime.current_task = asyncio.create_task(_run_navigation_task(websocket, runtime, session_id, instruction))
            elif action == "queue":
                await runtime.queued_instructions.put(instruction)
                await _send_step_and_screenshot(websocket, {"type": "queue", "content": f"Queued instruction: {instruction}"})
                runtime.settings = candidate_settings
                await _send_step_and_screenshot(websocket, {"type": "config", "content": "Session settings updated"})
                candidate_settings = data.get("settings", {})
                if not isinstance(candidate_settings, dict):
                    await websocket.send_json({"type": "error", "data": {"message": "Invalid config payload: settings must be an object"}})
                    continue
                runtime.settings = candidate_settings
                await _send_step_and_screenshot(websocket, {"type": "config", "content": "Session settings updated"})
                await _send_step(websocket, {"type": "queue", "content": f"Queued instruction: {instruction}"})
            elif action == "config":
                runtime.settings = data.get("settings", {})
                await _send_step(websocket, {"type": "config", "content": "Session settings updated"})
=======
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
>>>>>>> theirs
            elif action == "audio_chunk":
                transcript = await live_manager.process_audio(session_id, data.get("audio"))
                if transcript:
                    if runtime.task_running:
                        runtime.steering_context.append(transcript)
                    else:
<<<<<<< ours
                        runtime.current_task = asyncio.create_task(_run_navigation_task(websocket, runtime, session_id, transcript))
=======
                        _start_navigation_task(websocket, runtime, session_id, transcript)
>>>>>>> theirs
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


<<<<<<< ours
@app.post("/api/integrations/telegram/webhook/{integration_id}")
async def telegram_webhook(integration_id: str, request: Request):
    """Receive Telegram webhook updates.

    Validates the X-Telegram-Bot-Api-Secret-Token header before processing.
    """
    integration = telegram_registry.get_telegram(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not integration.validate_webhook_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid secret token")

    update = await request.json()
    await integration.handle_webhook_update(update)
    return {"ok": True}


@app.post("/api/integrations/telegram/register/{integration_id}")
async def register_telegram_integration(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Register or update an in-memory telegram integration instance."""
    config = TelegramConfig(
        bot_token=str(payload.get("bot_token", "")),
        delivery_mode=str(payload.get("delivery_mode", "polling")),
        webhook_url=str(payload.get("webhook_url", "")),
        webhook_secret=str(payload.get("webhook_secret", "")),
    )
    integration = TelegramIntegration(config)
    await integration.connect({
        "bot_token": config.bot_token,
        "delivery_mode": config.delivery_mode,
        "webhook_url": config.webhook_url,
        "webhook_secret": config.webhook_secret,
    })
    telegram_registry.upsert(integration_id, integration)
    test = await integration.test()
    return {"ok": True, "bot": test.get("bot"), "delivery_mode": test.get("delivery_mode")}

@app.post("/api/integrations/telegram/{integration_id}/test")
async def test_telegram_integration(integration_id: str) -> dict[str, Any]:
    """Run Telegram getMe + webhook status test."""
    integration = telegram_registry.get_telegram(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    return await integration.test()


@app.post("/api/integrations/telegram/{integration_id}/send_message")
async def telegram_send_message(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send a Telegram message using registered integration."""
    integration = telegram_registry.get_telegram(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    chat_id = int(payload.get("chat_id", 0))
    text = str(payload.get("text", ""))
    if integration.client is None:
        raise HTTPException(status_code=400, detail="Telegram client unavailable")
    result = await integration.client.send_message(chat_id=chat_id, text=text)
    return {"ok": True, "result": result}


@app.post("/api/integrations/telegram/{integration_id}/send_draft")
async def telegram_send_draft(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send progressive Telegram draft chunks and final message."""
    integration = telegram_registry.get_telegram(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    chat_id = int(payload.get("chat_id", 0))
    text = str(payload.get("text", ""))
    chunks = ["Thinking...", f"Thinking... {text[: max(5, len(text)//2)]}", text]
    result = await integration.stream_draft_then_send(chat_id=chat_id, chunks=chunks, draft_id=1, delay_between_chunks=0.15)
    return {"ok": True, "result": result}



=======
>>>>>>> theirs
if FRONTEND_DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str) -> FileResponse:
        """Serve compiled frontend files in production."""
<<<<<<< ours
        candidate = FRONTEND_DIST_DIR / full_path
=======
        candidate = (FRONTEND_DIST_DIR / full_path).resolve()
        try:
            candidate.relative_to(FRONTEND_DIST_DIR.resolve())
        except ValueError:
            return FileResponse(FRONTEND_DIST_DIR / "index.html")

>>>>>>> theirs
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
