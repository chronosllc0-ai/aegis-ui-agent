"""Live API session management for real-time voice interaction."""
import asyncio
import logging
import uuid
from google import genai
from src.utils.config import settings

logger = logging.getLogger(__name__)


class LiveSessionManager:
    """Manages Gemini Live API sessions for voice-based interaction."""

    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.sessions: dict[str, dict] = {}

    async def create_session(self) -> str:
        """Create a new Live API session."""
        session_id = str(uuid.uuid4())
        
        config = {
            "response_modalities": ["AUDIO", "TEXT"],
            "system_instruction": (
                "You are Aegis, a UI navigation assistant. You help users navigate "
                "websites and applications by voice. Describe what you see on screen "
                "and narrate your actions clearly. Be concise but informative."
            ),
        }
        
        self.sessions[session_id] = {
            "config": config,
            "active": True,
        }
        
        logger.info(f"Created Live session: {session_id}")
        return session_id

    async def process_audio(self, session_id: str, audio_data: bytes) -> str | None:
        """Process audio input and return transcribed text."""
        session = self.sessions.get(session_id)
        if not session or not session["active"]:
            return None
        
        # In production, this streams through the Live API WebSocket
        # For MVP, we use standard Gemini for audio transcription
        # TODO: Implement full Live API bidirectional streaming
        logger.info(f"Processing audio for session {session_id}")
        return None

    async def close_session(self, session_id: str):
        """Close a Live API session."""
        if session_id in self.sessions:
            self.sessions[session_id]["active"] = False
            del self.sessions[session_id]
            logger.info(f"Closed session: {session_id}")
