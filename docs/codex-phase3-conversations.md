# Codex Phase 3: Conversation Persistence

## Project Context
Aegis is a FastAPI + React/TypeScript app. Backend at repo root. Database: SQLAlchemy async (PostgreSQL/SQLite). Conversations were previously ephemeral (in-memory WebSocket sessions). Phase 1 added `Conversation` and `ConversationMessage` models. Phase 2 added admin endpoints to access conversations. Now we need to actually *persist* conversations from all platforms.

## What to implement
Create a conversation service and wire it into the WebSocket handler and integration webhook handlers so all messages are stored in the database.

## CRITICAL RULES
- Do NOT modify any frontend files
- Do NOT break existing WebSocket behavior — messages must still flow to the client exactly as before
- Do NOT modify: `orchestrator.py`, `session.py`, `navigator.py`, `analyzer.py`, `executor.py`, any file in `backend/providers/`, `backend/credit_rates.py`, `backend/credit_service.py`
- The conversation logging must be fire-and-forget — a database error during logging should NEVER break the user's session or cause a WebSocket disconnect
- Use `try/except` around all conversation logging calls

## Database models (from Phase 1)
```python
class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    platform = Column(String(50), nullable=False)      # "web" | "telegram" | "slack" | "discord"
    platform_chat_id = Column(String(255))
    title = Column(String(500))
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    conversation_id = Column(String(255), ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)           # "user" | "assistant" | "system"
    content = Column(Text, nullable=False)
    platform_message_id = Column(String(255))
    metadata_json = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

---

## 1. Create `backend/conversation_service.py`

```python
"""Conversation persistence service.

Provides helpers to create conversations and append messages from any platform.
All functions are designed to be called in a fire-and-forget pattern —
failures are logged but never raised to callers.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Conversation, ConversationMessage

logger = logging.getLogger(__name__)


async def get_or_create_conversation(
    session: AsyncSession,
    user_id: str,
    platform: str,
    platform_chat_id: str | None = None,
    title: str | None = None,
) -> Conversation:
    """Find an active conversation or create a new one.

    For web sessions, ``platform_chat_id`` is the WebSocket session ID.
    For integrations, it's the chat/channel ID from the platform.
    """
    # Look for an existing active conversation for this user + platform + chat
    query = select(Conversation).where(
        Conversation.user_id == user_id,
        Conversation.platform == platform,
        Conversation.status == "active",
    )
    if platform_chat_id:
        query = query.where(Conversation.platform_chat_id == platform_chat_id)
    query = query.order_by(Conversation.created_at.desc()).limit(1)
    result = await session.execute(query)
    existing = result.scalar_one_or_none()

    if existing:
        return existing

    conversation = Conversation(
        id=str(uuid4()),
        user_id=user_id,
        platform=platform,
        platform_chat_id=platform_chat_id,
        title=title or f"New {platform} conversation",
        status="active",
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def append_message(
    session: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict | None = None,
    platform_message_id: str | None = None,
) -> ConversationMessage | None:
    """Append a message to a conversation. Returns the message or None on failure."""
    if not content or not content.strip():
        return None

    message = ConversationMessage(
        id=str(uuid4()),
        conversation_id=conversation_id,
        role=role,
        content=content.strip(),
        platform_message_id=platform_message_id,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    session.add(message)
    await session.commit()
    return message


async def update_conversation_title(
    session: AsyncSession,
    conversation_id: str,
    title: str,
) -> None:
    """Update the title of a conversation (usually from the first user message)."""
    conversation = await session.get(Conversation, conversation_id)
    if conversation:
        conversation.title = title[:500]
        await session.commit()
```

## 2. Wire into WebSocket handler in `main.py`

This is the most delicate part. The WebSocket handler in `main.py` (`websocket_navigate` function) needs to log conversations WITHOUT breaking the existing flow.

### 2a. Add imports at the top of `main.py`

Add (with other backend imports):
```python
from backend.conversation_service import get_or_create_conversation, append_message, update_conversation_title
from backend.database import _session_factory
```

Note: We use `_session_factory` directly because WebSocket handlers don't use FastAPI's `Depends()` — they need to manually create sessions.

### 2b. Modify `websocket_navigate` function

Add conversation tracking to the session. The changes are:

1. After `session_id = await live_manager.create_session()`, add:
```python
    conversation_id: str | None = None
    ws_user_uid: str | None = None

    # Try to extract user from session cookie for conversation logging
    try:
        cookies = websocket.cookies
        token = cookies.get("aegis_session")
        ws_payload = _verify_session(token)
        if ws_payload:
            ws_user_uid = ws_payload.get("uid")
    except Exception:  # noqa: BLE001
        pass
```

2. Inside the `if action == "navigate":` block, AFTER `_start_navigation_task(...)` is called, add conversation creation:
```python
                # Log conversation
                if ws_user_uid and _session_factory:
                    try:
                        async with _session_factory() as db_sess:
                            conv = await get_or_create_conversation(db_sess, ws_user_uid, "web", session_id)
                            conversation_id = conv.id
                            await append_message(db_sess, conversation_id, "user", instruction)
                            await update_conversation_title(db_sess, conversation_id, instruction[:200])
                    except Exception:  # noqa: BLE001
                        logger.debug("Conversation logging failed", exc_info=True)
```

3. Inside `_run_navigation_task`, after `await websocket.send_json({"type": "result", ...})` (the success case), add:
```python
        # Log assistant result
        if hasattr(websocket, '_conversation_id_holder'):
            pass  # We'll use a different approach
```

Actually, a cleaner approach: pass `conversation_id` and `ws_user_uid` into the runtime object.

**Better approach:** Add `conversation_id` and `user_uid` fields to `SessionRuntime`:
```python
class SessionRuntime:
    def __init__(self) -> None:
        self.task_running = False
        self.current_task: asyncio.Task[None] | None = None
        self.cancel_event = asyncio.Event()
        self.steering_context: list[str] = []
        self.queued_instructions: list[str] = []
        self.settings: dict[str, Any] = {}
        self.conversation_id: str | None = None
        self.user_uid: str | None = None
```

Then in `websocket_navigate`:
```python
    runtime.user_uid = ws_user_uid
```

And in the `navigate` action handler:
```python
                if runtime.user_uid and _session_factory:
                    try:
                        async with _session_factory() as db_sess:
                            conv = await get_or_create_conversation(db_sess, runtime.user_uid, "web", session_id)
                            runtime.conversation_id = conv.id
                            await append_message(db_sess, runtime.conversation_id, "user", instruction)
                            await update_conversation_title(db_sess, runtime.conversation_id, instruction[:200])
                    except Exception:  # noqa: BLE001
                        logger.debug("Conversation logging failed", exc_info=True)
```

Also log steer actions:
```python
            elif action == "steer":
                runtime.steering_context.append(instruction)
                await _send_step(websocket, {"type": "steer", "content": f"Steering note added: {instruction}"})
                # Log steering message
                if runtime.conversation_id and _session_factory:
                    try:
                        async with _session_factory() as db_sess:
                            await append_message(db_sess, runtime.conversation_id, "user", f"[steer] {instruction}")
                    except Exception:  # noqa: BLE001
                        logger.debug("Conversation steer logging failed", exc_info=True)
```

And in `_run_navigation_task`, after sending the result:
```python
        # Log result to conversation
        if runtime.conversation_id and _session_factory:
            try:
                async with _session_factory() as db_sess:
                    summary = result.get("status", "completed") if isinstance(result, dict) else "completed"
                    await append_message(db_sess, runtime.conversation_id, "assistant", f"Task {summary}: {instruction}")
            except Exception:  # noqa: BLE001
                logger.debug("Conversation result logging failed", exc_info=True)
```

## 3. Wire into integration webhooks

### 3a. Telegram webhook (`telegram_webhook` in `main.py`)

After `result = await integration.execute_tool("telegram_webhook_update", {"update": update})`, add logging:

```python
    # Log conversation
    if _session_factory:
        try:
            async with _session_factory() as db_sess:
                # Extract chat_id and text from the update
                message = update.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                text_content = message.get("text", "")
                if chat_id and text_content:
                    conv = await get_or_create_conversation(db_sess, f"telegram:{chat_id}", "telegram", chat_id)
                    await append_message(db_sess, conv.id, "user", text_content)
        except Exception:  # noqa: BLE001
            logger.debug("Telegram conversation logging failed", exc_info=True)
```

### 3b. Slack send message (`slack_send_message` in `main.py`)

After `result = await integration.execute_tool(...)`, add:
```python
    if _session_factory:
        try:
            async with _session_factory() as db_sess:
                conv = await get_or_create_conversation(db_sess, f"slack:{integration_id}", "slack", channel)
                await append_message(db_sess, conv.id, "assistant", text)
        except Exception:  # noqa: BLE001
            logger.debug("Slack conversation logging failed", exc_info=True)
```

### 3c. Discord send message (`discord_send_message` in `main.py`)

Same pattern as Slack:
```python
    if _session_factory:
        try:
            async with _session_factory() as db_sess:
                conv = await get_or_create_conversation(db_sess, f"discord:{integration_id}", "discord", channel)
                await append_message(db_sess, conv.id, "assistant", text)
        except Exception:  # noqa: BLE001
            logger.debug("Discord conversation logging failed", exc_info=True)
```

---

## Verification
1. All existing tests pass: `pytest tests/ -v`
2. WebSocket connections still work — navigate, steer, queue, interrupt, audio all function normally
3. Integration webhook endpoints still return correct responses
4. No new import errors on startup
5. `frontend/` is completely untouched — `npm run build` in `frontend/` still passes
