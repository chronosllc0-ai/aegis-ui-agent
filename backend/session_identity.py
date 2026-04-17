"""Session identity helpers and conversation compatibility bridge."""

from __future__ import annotations

from dataclasses import dataclass

SESSION_MAIN_ID = "agent:main:main"


@dataclass(frozen=True)
class SessionIdentity:
    """Canonical structured session identity for channel/account chats."""

    channel: str
    account: str
    chat_type: str
    peer_id: str

    def to_session_id(self) -> str:
        """Serialize to canonical session id string."""
        return f"agent:main:{self.channel}:{self.account}:{self.chat_type}:{self.peer_id}"


def conversation_id_to_session_id(conversation_id: str) -> str:
    """Map legacy conversation_id into a deterministic canonical session_id."""
    normalized = str(conversation_id or "").strip()
    if not normalized:
        return SESSION_MAIN_ID
    return SessionIdentity(channel="web", account="legacy", chat_type="conversation", peer_id=normalized).to_session_id()


def session_id_to_conversation_id(session_id: str) -> str | None:
    """Map canonical session_id back to legacy conversation_id when possible."""
    raw = str(session_id or "").strip()
    if not raw or raw == SESSION_MAIN_ID:
        return None
    parts = raw.split(":")
    if len(parts) == 6 and parts[:3] == ["agent", "main", "web"] and parts[3] == "legacy" and parts[4] == "conversation":
        return parts[5] or None
    return None


def normalize_or_bridge_session_id(session_id: str, *, fallback_conversation_id: str | None = None) -> str:
    """Return canonical session id, bridging from legacy ids when needed."""
    normalized = str(session_id or "").strip()
    if normalized.startswith("agent:main:"):
        return normalized
    if normalized:
        return conversation_id_to_session_id(normalized)
    if fallback_conversation_id:
        return conversation_id_to_session_id(fallback_conversation_id)
    return SESSION_MAIN_ID
