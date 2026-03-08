"""Live API session management for real-time voice interaction."""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class LiveSessionManager:
    """Manages per-client Live API session metadata."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}

    async def create_session(self) -> str:
        """Create and register a new session ID."""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {"active": True}
        logger.info("Created Live session %s", session_id)
        return session_id

    async def process_audio(self, session_id: str, audio_data: bytes | str | None) -> str | None:
        """Process incoming audio payload.

        Current scaffold returns ``None`` until full Gemini Live streaming is implemented.
        """
        _ = audio_data
        session = self.sessions.get(session_id)
        if not session or not session["active"]:
            return None
        logger.info("Audio chunk received for session %s", session_id)
        return None

    async def close_session(self, session_id: str) -> None:
        """Deactivate and remove a session."""
        if session_id in self.sessions:
            self.sessions[session_id]["active"] = False
            del self.sessions[session_id]
            logger.info("Closed session %s", session_id)
