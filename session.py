"""Live API session management for real-time voice interaction."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
import logging
from typing import Any
import uuid

from google import genai

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class LiveSessionState:
    """Runtime state for a single Live API session."""

    session_id: str
    active: bool = True
    connection: Any | None = None
    session: Any | None = None
    receiver_task: asyncio.Task[None] | None = None
    transcript_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    last_transcript: str | None = None


class LiveSessionManager:
    """Manages per-client Live API session metadata and audio streaming."""

    def __init__(self) -> None:
        self.sessions: dict[str, LiveSessionState] = {}
        self._client: genai.Client | None = None
        self._lock = asyncio.Lock()

    async def create_session(self) -> str:
        """Create and register a new session ID."""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = LiveSessionState(session_id=session_id)
        logger.info("Created Live session %s", session_id)
        return session_id

    async def process_audio(self, session_id: str, audio_data: bytes | str | None) -> str | None:
        """Process incoming audio payload and return a transcript when available."""
        state = self.sessions.get(session_id)
        if not state or not state.active:
            return None

        if audio_data is None:
            return None

        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set; skipping Live API audio processing.")
            return None

        await self._ensure_live_session(state)
        if state.session is None:
            return None

        try:
            audio_bytes = self._decode_audio(audio_data)
        except ValueError as exc:
            logger.warning("Invalid audio payload for session %s: %s", session_id, exc)
            return None

        try:
            await state.session.send_realtime_input(
                audio={"data": audio_bytes, "mime_type": "audio/pcm"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send audio chunk for session %s: %s", session_id, exc)
            await self._close_live_session(state)
            return None

        transcript: str | None = None
        while not state.transcript_queue.empty():
            try:
                transcript = state.transcript_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        return transcript

    async def close_session(self, session_id: str) -> None:
        """Deactivate, close, and remove a session."""
        state = self.sessions.pop(session_id, None)
        if not state:
            return
        state.active = False
        await self._close_live_session(state)
        logger.info("Closed session %s", session_id)

    async def _ensure_live_session(self, state: LiveSessionState) -> None:
        if state.session is not None:
            return

        async with self._lock:
            if state.session is not None:
                return
            if self._client is None:
                self._client = genai.Client(api_key=settings.GEMINI_API_KEY)

            config = {
                "response_modalities": ["TEXT"],
            }
            connection = self._client.aio.live.connect(
                model=settings.GEMINI_LIVE_MODEL,
                config=config,
            )
            state.connection = connection
            state.session = await connection.__aenter__()
            state.receiver_task = asyncio.create_task(self._receive_loop(state))
            logger.info("Live API session connected for %s", state.session_id)

    async def _receive_loop(self, state: LiveSessionState) -> None:
        try:
            if state.session is None:
                return
            async for response in state.session.receive():
                if not state.active:
                    break
                transcript = self._extract_text(response)
                if transcript and transcript != state.last_transcript:
                    state.last_transcript = transcript
                    await state.transcript_queue.put(transcript)
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Live API receive loop failed for %s: %s", state.session_id, exc)

    async def _close_live_session(self, state: LiveSessionState) -> None:
        if state.receiver_task is not None:
            state.receiver_task.cancel()
            try:
                await state.receiver_task
            except asyncio.CancelledError:
                pass
        if state.connection is not None:
            try:
                await state.connection.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to close Live API connection for %s", state.session_id)
        state.connection = None
        state.session = None
        state.receiver_task = None

    @staticmethod
    def _decode_audio(audio_data: bytes | str) -> bytes:
        if isinstance(audio_data, bytes):
            return audio_data
        if isinstance(audio_data, str):
            data = audio_data.strip()
            if not data:
                raise ValueError("Empty audio payload")
            try:
                return base64.b64decode(data, validate=True)
            except ValueError:
                return base64.b64decode(data)
        raise ValueError("Unsupported audio payload type")

    @staticmethod
    def _extract_text(response: Any) -> str | None:
        """Best-effort text extraction from Live API responses."""
        def search(payload: Any, depth: int = 0) -> str | None:
            if depth > 6:
                return None
            if isinstance(payload, str):
                text = payload.strip()
                return text if text else None
            if isinstance(payload, dict):
                for key in ("text", "transcript"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                for key in ("content", "contents", "parts", "candidates", "outputs", "response", "server_content"):
                    if key in payload:
                        found = search(payload[key], depth + 1)
                        if found:
                            return found
            if isinstance(payload, list):
                for item in payload:
                    found = search(item, depth + 1)
                    if found:
                        return found
            return None

        if hasattr(response, "model_dump"):
            try:
                return search(response.model_dump())
            except Exception:  # noqa: BLE001
                pass
        if hasattr(response, "to_dict"):
            try:
                return search(response.to_dict())
            except Exception:  # noqa: BLE001
                pass
        if hasattr(response, "__dict__"):
            try:
                return search(response.__dict__)
            except Exception:  # noqa: BLE001
                pass
        return search(response)
