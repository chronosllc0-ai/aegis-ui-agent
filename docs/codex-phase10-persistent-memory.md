# Codex Phase 10: Persistent Memory System (pgvector)

## Project Context
Aegis is a FastAPI + React/TypeScript app. Backend at repo root. Frontend at `frontend/`. Database: SQLAlchemy async (PostgreSQL/SQLite). The backend currently has no memory across sessions — when a user starts a new conversation, all context from previous sessions is lost. The orchestrator processes each task in isolation with no recall of past interactions, preferences, or learned facts.

This phase adds a persistent memory system that stores and retrieves user-specific knowledge fragments using vector embeddings (pgvector) for semantic search. The system learns from conversations and user-provided facts, and injects relevant memories as context before each LLM call.

## What to implement
1. A `backend/memory/` module with embedding generation, vector storage, and semantic retrieval
2. Database models for memory entries with pgvector support (with SQLite fallback using cosine similarity on JSON arrays)
3. API endpoints for viewing, creating, editing, and deleting memories
4. A frontend Memory tab in the settings page for users to manage their memories
5. A memory injection pipeline that retrieves relevant memories before task execution

## CRITICAL RULES
- Do NOT modify: `orchestrator.py`, `session.py`, `navigator.py`, `analyzer.py`, `executor.py`, `mcp_client.py`
- Do NOT modify: any existing file in `backend/providers/`, `backend/connectors/`, `backend/admin/`, `backend/planner/`, `backend/gallery/`
- Do NOT modify: `backend/credit_rates.py`, `backend/credit_service.py`, `backend/key_management.py`, `backend/conversation_service.py`
- Do NOT modify: `frontend/src/components/settings/APIKeysTab.tsx`, `frontend/src/components/settings/ProfileTab.tsx`, `frontend/src/components/settings/AgentConfigTab.tsx`
- Do NOT modify: `frontend/src/components/LandingPage.tsx`, `frontend/src/components/AuthPage.tsx`
- Do NOT modify: `auth.py`
- You MAY add new imports to `backend/database.py` and add new model classes at the BOTTOM (after existing models)
- You MAY add a new tab import in `frontend/src/components/settings/SettingsPage.tsx`
- ESLint strict: NO `setState` in `useEffect` bodies, NO ref access during render, hooks and components in separate files if both are exported
- Tailwind v4 dark theme: `bg-[#111]`, `bg-[#1a1a1a]`, `border-[#2a2a2a]`, `text-zinc-*`
- Use `apiUrl('/path')` from `frontend/src/lib/api.ts` for ALL frontend API calls

---

## Database Models

Add these to `backend/database.py` AFTER the existing `SupportMessage` class (and after `TaskStep` if Phase 7 was implemented):

```python
class MemoryEntry(Base):
    """A persistent memory fragment for a user.

    Stores facts, preferences, and learned information across sessions.
    Embeddings are stored as JSON arrays of floats (for portability).
    When pgvector is available, a separate ``memory_embeddings`` table
    with a ``vector`` column accelerates similarity search.
    """

    __tablename__ = "memory_entries"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    category = Column(String(50), default="general")  # general | preference | fact | instruction | context
    source = Column(String(50), default="conversation")  # conversation | manual | system
    source_conversation_id = Column(String(255), nullable=True)
    embedding = Column(Text, nullable=True)  # JSON array of floats (1536 dims for OpenAI, 768 for others)
    embedding_model = Column(String(100), nullable=True)
    importance = Column(Float, default=0.5)  # 0.0 (low) to 1.0 (critical)
    access_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    is_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

---

## 1. Create `backend/memory/__init__.py`

```python
"""Persistent memory system with vector-based semantic retrieval."""

from .service import MemoryService
from .embeddings import get_embedding

__all__ = ["MemoryService", "get_embedding"]
```

## 2. Create `backend/memory/embeddings.py`

Generates embeddings using the user's configured provider. Falls back to a simple TF-IDF-like hash embedding when no embedding API is available.

```python
"""Embedding generation for the memory system.

Supports OpenAI embeddings (text-embedding-3-small) as primary,
with a simple fallback hash-based embedding for development.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from typing import Any

import httpx

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536  # OpenAI text-embedding-3-small


async def get_embedding(
    text: str,
    api_key: str | None = None,
    provider: str = "openai",
) -> list[float]:
    """Generate an embedding vector for the given text.

    Uses OpenAI's embedding API when an API key is available.
    Falls back to a deterministic hash-based embedding for development.
    """
    if api_key and provider == "openai":
        return await _openai_embedding(text, api_key)
    # Fallback: deterministic hash embedding
    return _hash_embedding(text)


async def _openai_embedding(text: str, api_key: str) -> list[float]:
    """Call OpenAI embeddings API."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "text-embedding-3-small", "input": text},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
    except Exception:
        logger.warning("OpenAI embedding failed, using hash fallback", exc_info=True)
        return _hash_embedding(text)


def _hash_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic pseudo-embedding from text hash.

    NOT suitable for production semantic search, but allows the system
    to function during development without an embedding API.
    """
    # Create a deterministic seed from the text
    text_bytes = text.lower().strip().encode("utf-8")
    digest = hashlib.sha512(text_bytes).hexdigest()

    # Generate dim floats from repeated hashing
    vector: list[float] = []
    seed = digest
    while len(vector) < dim:
        seed = hashlib.sha256(seed.encode()).hexdigest()
        for i in range(0, len(seed) - 1, 2):
            if len(vector) >= dim:
                break
            byte_val = int(seed[i:i + 2], 16)
            vector.append((byte_val / 255.0) * 2 - 1)  # normalize to [-1, 1]

    # Normalize to unit vector
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
```

## 3. Create `backend/memory/service.py`

```python
"""Memory CRUD and semantic retrieval service."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update, delete, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import MemoryEntry
from backend.memory.embeddings import get_embedding, cosine_similarity

logger = logging.getLogger(__name__)


class MemoryService:
    """Manages persistent memory entries for users."""

    @staticmethod
    async def store(
        session: AsyncSession,
        user_id: str,
        content: str,
        category: str = "general",
        source: str = "manual",
        source_conversation_id: str | None = None,
        importance: float = 0.5,
        api_key: str | None = None,
        embedding_provider: str = "openai",
    ) -> dict:
        """Store a new memory entry with embedding."""
        embedding = await get_embedding(content, api_key, embedding_provider)

        entry = MemoryEntry(
            id=str(uuid4()),
            user_id=user_id,
            content=content,
            category=category,
            source=source,
            source_conversation_id=source_conversation_id,
            embedding=json.dumps(embedding),
            embedding_model=f"{embedding_provider}/text-embedding-3-small" if api_key else "hash-fallback",
            importance=importance,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)

        return _entry_to_dict(entry)

    @staticmethod
    async def recall(
        session: AsyncSession,
        user_id: str,
        query: str,
        limit: int = 10,
        min_similarity: float = 0.3,
        category: str | None = None,
        api_key: str | None = None,
        embedding_provider: str = "openai",
    ) -> list[dict]:
        """Retrieve the most relevant memories for a query using semantic search.

        Falls back to keyword search if embeddings are unavailable.
        """
        # Generate query embedding
        query_embedding = await get_embedding(query, api_key, embedding_provider)

        # Build base query
        stmt = select(MemoryEntry).where(MemoryEntry.user_id == user_id)
        if category:
            stmt = stmt.where(MemoryEntry.category == category)

        result = await session.execute(stmt)
        entries = result.scalars().all()

        if not entries:
            return []

        # Score and rank by cosine similarity
        scored: list[tuple[float, MemoryEntry]] = []
        for entry in entries:
            if entry.embedding:
                entry_emb = json.loads(entry.embedding)
                sim = cosine_similarity(query_embedding, entry_emb)
                if sim >= min_similarity:
                    # Boost pinned entries
                    effective_score = sim * (1.2 if entry.is_pinned else 1.0)
                    scored.append((effective_score, entry))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]

        # Update access counts
        for _, entry in top:
            entry.access_count = (entry.access_count or 0) + 1
            entry.last_accessed_at = datetime.now(timezone.utc)
        await session.commit()

        return [
            {**_entry_to_dict(entry), "relevance_score": round(score, 4)}
            for score, entry in top
        ]

    @staticmethod
    async def list_memories(
        session: AsyncSession,
        user_id: str,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List all memories for a user, newest first."""
        stmt = (
            select(MemoryEntry)
            .where(MemoryEntry.user_id == user_id)
            .order_by(MemoryEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if category:
            stmt = stmt.where(MemoryEntry.category == category)

        result = await session.execute(stmt)
        return [_entry_to_dict(e) for e in result.scalars().all()]

    @staticmethod
    async def get_memory(session: AsyncSession, memory_id: str, user_id: str) -> dict | None:
        """Get a single memory by ID."""
        result = await session.execute(
            select(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.user_id == user_id)
        )
        entry = result.scalar_one_or_none()
        return _entry_to_dict(entry) if entry else None

    @staticmethod
    async def update_memory(
        session: AsyncSession,
        memory_id: str,
        user_id: str,
        content: str | None = None,
        category: str | None = None,
        importance: float | None = None,
        is_pinned: bool | None = None,
        api_key: str | None = None,
        embedding_provider: str = "openai",
    ) -> dict | None:
        """Update a memory entry. Re-generates embedding if content changes."""
        result = await session.execute(
            select(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.user_id == user_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return None

        if content is not None and content != entry.content:
            entry.content = content
            embedding = await get_embedding(content, api_key, embedding_provider)
            entry.embedding = json.dumps(embedding)
            entry.embedding_model = f"{embedding_provider}/text-embedding-3-small" if api_key else "hash-fallback"
        if category is not None:
            entry.category = category
        if importance is not None:
            entry.importance = importance
        if is_pinned is not None:
            entry.is_pinned = is_pinned

        await session.commit()
        await session.refresh(entry)
        return _entry_to_dict(entry)

    @staticmethod
    async def delete_memory(session: AsyncSession, memory_id: str, user_id: str) -> bool:
        """Delete a memory entry."""
        result = await session.execute(
            delete(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.user_id == user_id)
        )
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def get_stats(session: AsyncSession, user_id: str) -> dict:
        """Get memory usage statistics."""
        result = await session.execute(
            select(
                sa_func.count(MemoryEntry.id),
                sa_func.count(sa_func.nullif(MemoryEntry.is_pinned, False)),
            ).where(MemoryEntry.user_id == user_id)
        )
        row = result.one()
        total_count = row[0]
        pinned_count = row[1]

        # Count by category
        cat_result = await session.execute(
            select(MemoryEntry.category, sa_func.count(MemoryEntry.id))
            .where(MemoryEntry.user_id == user_id)
            .group_by(MemoryEntry.category)
        )
        categories = {cat: count for cat, count in cat_result.all()}

        return {
            "total_memories": total_count,
            "pinned_memories": pinned_count,
            "by_category": categories,
        }

    @staticmethod
    async def build_context(
        session: AsyncSession,
        user_id: str,
        query: str,
        max_memories: int = 5,
        api_key: str | None = None,
        embedding_provider: str = "openai",
    ) -> str:
        """Build a context string from relevant memories to inject before an LLM call.

        Returns a formatted string with the most relevant memories, or empty string
        if no relevant memories are found.
        """
        memories = await MemoryService.recall(
            session, user_id, query,
            limit=max_memories,
            min_similarity=0.35,
            api_key=api_key,
            embedding_provider=embedding_provider,
        )
        if not memories:
            return ""

        lines = ["[User Memory Context]"]
        for m in memories:
            pin_marker = " [pinned]" if m.get("is_pinned") else ""
            lines.append(f"- ({m['category']}{pin_marker}) {m['content']}")
        lines.append("[End Memory Context]")
        return "\n".join(lines)


def _entry_to_dict(entry: MemoryEntry) -> dict:
    """Serialize a MemoryEntry to a dict (excluding raw embedding)."""
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "content": entry.content,
        "category": entry.category,
        "source": entry.source,
        "source_conversation_id": entry.source_conversation_id,
        "embedding_model": entry.embedding_model,
        "importance": entry.importance,
        "access_count": entry.access_count,
        "is_pinned": entry.is_pinned,
        "last_accessed_at": entry.last_accessed_at.isoformat() if entry.last_accessed_at else None,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }
```

## 4. Create `backend/memory/router.py`

```python
"""API routes for memory management."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import get_session
from backend.key_management import KeyManager
from backend.memory.service import MemoryService
from config import settings

logger = logging.getLogger(__name__)
memory_router = APIRouter(prefix="/api/memory", tags=["memory"])
key_manager = KeyManager(settings.ENCRYPTION_SECRET)


def _get_user_uid(request) -> str:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload["uid"]


async def _get_user_embedding_key(db: AsyncSession, uid: str) -> tuple[str | None, str]:
    """Get the user's OpenAI key for embeddings, or fall back to platform key."""
    key = await key_manager.get_key(db, uid, "openai")
    if key:
        return key, "openai"
    platform_key = getattr(settings, "OPENAI_API_KEY", "")
    if platform_key:
        return platform_key, "openai"
    return None, "hash"


@memory_router.get("/")
async def list_memories(
    request: Any,
    db: AsyncSession = Depends(get_session),
    category: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List user's memories."""
    uid = _get_user_uid(request)
    memories = await MemoryService.list_memories(db, uid, category=category, limit=limit, offset=offset)
    return {"ok": True, "memories": memories}


@memory_router.post("/")
async def create_memory(
    payload: dict[str, Any],
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a new memory entry.

    Body: { "content": "...", "category": "general|preference|fact|instruction|context", "importance": 0.5 }
    """
    uid = _get_user_uid(request)
    content = payload.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    if len(content) > 10000:
        raise HTTPException(status_code=400, detail="Memory content too long (max 10,000 characters)")

    category = payload.get("category", "general")
    importance = payload.get("importance", 0.5)

    api_key, provider = await _get_user_embedding_key(db, uid)

    memory = await MemoryService.store(
        db, uid, content,
        category=category,
        source="manual",
        importance=importance,
        api_key=api_key,
        embedding_provider=provider,
    )
    return {"ok": True, "memory": memory}


@memory_router.get("/search")
async def search_memories(
    request: Any,
    db: AsyncSession = Depends(get_session),
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    category: str | None = Query(None),
) -> dict[str, Any]:
    """Semantic search across memories."""
    uid = _get_user_uid(request)
    api_key, provider = await _get_user_embedding_key(db, uid)

    memories = await MemoryService.recall(
        db, uid, q,
        limit=limit,
        category=category,
        api_key=api_key,
        embedding_provider=provider,
    )
    return {"ok": True, "memories": memories}


@memory_router.get("/stats")
async def memory_stats(
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get memory usage statistics."""
    uid = _get_user_uid(request)
    stats = await MemoryService.get_stats(db, uid)
    return {"ok": True, "stats": stats}


@memory_router.get("/{memory_id}")
async def get_memory(
    memory_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a single memory."""
    uid = _get_user_uid(request)
    memory = await MemoryService.get_memory(db, memory_id, uid)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": memory}


@memory_router.put("/{memory_id}")
async def update_memory(
    memory_id: str,
    payload: dict[str, Any],
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update a memory entry.

    Body: { "content": "...", "category": "...", "importance": 0.5, "is_pinned": false }
    """
    uid = _get_user_uid(request)
    api_key, provider = await _get_user_embedding_key(db, uid)

    memory = await MemoryService.update_memory(
        db, memory_id, uid,
        content=payload.get("content"),
        category=payload.get("category"),
        importance=payload.get("importance"),
        is_pinned=payload.get("is_pinned"),
        api_key=api_key,
        embedding_provider=provider,
    )
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": memory}


@memory_router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Delete a memory entry."""
    uid = _get_user_uid(request)
    ok = await MemoryService.delete_memory(db, memory_id, uid)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}
```

## 5. Register router in `main.py`

Add import:
```python
from backend.memory.router import memory_router
```

Add registration:
```python
app.include_router(memory_router)
```

## 6. Create `frontend/src/hooks/useMemory.ts`

```typescript
import { useCallback, useState } from 'react'
import { apiUrl } from '../lib/api'

export type MemoryEntry = {
  id: string
  user_id: string
  content: string
  category: string
  source: string
  source_conversation_id: string | null
  embedding_model: string | null
  importance: number
  access_count: number
  is_pinned: boolean
  last_accessed_at: string | null
  created_at: string | null
  updated_at: string | null
  relevance_score?: number
}

export type MemoryStats = {
  total_memories: number
  pinned_memories: number
  by_category: Record<string, number>
}

export function useMemory() {
  const [memories, setMemories] = useState<MemoryEntry[]>([])
  const [stats, setStats] = useState<MemoryStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchMemories = useCallback(async (category?: string) => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (category) params.set('category', category)
      const resp = await fetch(apiUrl(`/api/memory/?${params}`), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setMemories(data.memories)
      else setError(data.detail || 'Failed to load memories')
    } catch {
      setError('Failed to load memories')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/memory/stats'), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setStats(data.stats)
    } catch { /* silent */ }
  }, [])

  const createMemory = useCallback(async (content: string, category: string = 'general', importance: number = 0.5): Promise<MemoryEntry | null> => {
    try {
      const resp = await fetch(apiUrl('/api/memory/'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, category, importance }),
      })
      const data = await resp.json()
      if (data.ok) {
        setMemories((prev) => [data.memory, ...prev])
        return data.memory
      }
      return null
    } catch {
      return null
    }
  }, [])

  const updateMemory = useCallback(async (id: string, updates: Partial<Pick<MemoryEntry, 'content' | 'category' | 'importance' | 'is_pinned'>>): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/memory/${id}`), {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      })
      const data = await resp.json()
      if (data.ok) {
        setMemories((prev) => prev.map((m) => (m.id === id ? data.memory : m)))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  const deleteMemory = useCallback(async (id: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/memory/${id}`), {
        method: 'DELETE',
        credentials: 'include',
      })
      const data = await resp.json()
      if (data.ok) {
        setMemories((prev) => prev.filter((m) => m.id !== id))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  const searchMemories = useCallback(async (query: string, category?: string): Promise<MemoryEntry[]> => {
    try {
      const params = new URLSearchParams({ q: query })
      if (category) params.set('category', category)
      const resp = await fetch(apiUrl(`/api/memory/search?${params}`), { credentials: 'include' })
      const data = await resp.json()
      return data.ok ? data.memories : []
    } catch {
      return []
    }
  }, [])

  return {
    memories, stats, loading, error,
    fetchMemories, fetchStats, createMemory, updateMemory, deleteMemory, searchMemories,
  }
}
```

## 7. Create `frontend/src/components/settings/MemoryTab.tsx`

```tsx
import { useCallback, useEffect, useState } from 'react'
import { useMemory } from '../../hooks/useMemory'
import type { MemoryEntry } from '../../hooks/useMemory'

const CATEGORIES = ['general', 'preference', 'fact', 'instruction', 'context'] as const

const CATEGORY_COLORS: Record<string, string> = {
  general: 'bg-zinc-700 text-zinc-300',
  preference: 'bg-purple-900/40 text-purple-300',
  fact: 'bg-blue-900/40 text-blue-300',
  instruction: 'bg-amber-900/40 text-amber-300',
  context: 'bg-emerald-900/40 text-emerald-300',
}

export function MemoryTab() {
  const {
    memories, stats, loading, error,
    fetchMemories, fetchStats, createMemory, updateMemory, deleteMemory, searchMemories,
  } = useMemory()

  const [activeCategory, setActiveCategory] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<MemoryEntry[] | null>(null)
  const [newContent, setNewContent] = useState('')
  const [newCategory, setNewCategory] = useState<string>('general')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editContent, setEditContent] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    fetchMemories(activeCategory || undefined)
    fetchStats()
  }, [fetchMemories, fetchStats, activeCategory])

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      setSearchResults(null)
      return
    }
    const results = await searchMemories(searchQuery, activeCategory || undefined)
    setSearchResults(results)
  }, [searchQuery, activeCategory, searchMemories])

  const handleCreate = async () => {
    if (!newContent.trim()) return
    setCreating(true)
    const result = await createMemory(newContent.trim(), newCategory)
    if (result) {
      setNewContent('')
      await fetchStats()
    }
    setCreating(false)
  }

  const handleDelete = async (id: string) => {
    await deleteMemory(id)
    await fetchStats()
  }

  const handleTogglePin = async (memory: MemoryEntry) => {
    await updateMemory(memory.id, { is_pinned: !memory.is_pinned })
  }

  const handleSaveEdit = async (id: string) => {
    if (!editContent.trim()) return
    await updateMemory(id, { content: editContent.trim() })
    setEditingId(null)
    setEditContent('')
  }

  const displayMemories = searchResults ?? memories

  return (
    <div className="space-y-6">
      {/* Stats bar */}
      {stats && (
        <div className="flex gap-4 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-4">
          <div>
            <span className="text-lg font-semibold text-white">{stats.total_memories}</span>
            <span className="ml-1 text-xs text-zinc-500">memories</span>
          </div>
          <div>
            <span className="text-lg font-semibold text-white">{stats.pinned_memories}</span>
            <span className="ml-1 text-xs text-zinc-500">pinned</span>
          </div>
          <div className="flex-1" />
          {Object.entries(stats.by_category).map(([cat, count]) => (
            <div key={cat} className="text-right">
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${CATEGORY_COLORS[cat] || 'bg-zinc-700 text-zinc-300'}`}>
                {cat}: {count}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Add new memory */}
      <div className="rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-4">
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">Add Memory</h4>
        <textarea
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          placeholder="Tell Aegis something to remember (e.g., preferences, facts, instructions)..."
          className="mb-2 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
          rows={2}
        />
        <div className="flex items-center gap-2">
          <select
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            className="rounded-lg border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-300"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <div className="flex-1" />
          <button
            type="button"
            onClick={handleCreate}
            disabled={creating || !newContent.trim()}
            className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {creating ? 'Saving...' : 'Save Memory'}
          </button>
        </div>
      </div>

      {/* Search + filter */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="Search memories semantically..."
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
        />
        <button type="button" onClick={handleSearch} className="rounded-lg bg-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:bg-zinc-600">
          Search
        </button>
        {searchResults && (
          <button type="button" onClick={() => { setSearchResults(null); setSearchQuery('') }} className="text-xs text-zinc-500 hover:text-zinc-300">
            Clear
          </button>
        )}
      </div>

      {/* Category tabs */}
      <div className="flex gap-1.5">
        <button
          type="button"
          onClick={() => setActiveCategory(null)}
          className={`rounded-full px-3 py-1 text-xs font-medium ${!activeCategory ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}
        >
          All
        </button>
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setActiveCategory(cat)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${activeCategory === cat ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'}`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Memory list */}
      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading ? (
        <div className="flex justify-center py-8">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
        </div>
      ) : displayMemories.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">
          {searchResults ? 'No matching memories found' : 'No memories yet. Add one above to get started.'}
        </p>
      ) : (
        <div className="space-y-2">
          {displayMemories.map((m) => (
            <div key={m.id} className="group rounded-xl border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="flex items-start gap-2">
                <button type="button" onClick={() => handleTogglePin(m)} className={`mt-0.5 text-sm ${m.is_pinned ? 'text-amber-400' : 'text-zinc-600 hover:text-zinc-400'}`}>
                  {m.is_pinned ? '★' : '☆'}
                </button>
                <div className="min-w-0 flex-1">
                  {editingId === m.id ? (
                    <div className="space-y-2">
                      <textarea
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                        className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none"
                        rows={3}
                      />
                      <div className="flex gap-2">
                        <button type="button" onClick={() => handleSaveEdit(m.id)} className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-500">Save</button>
                        <button type="button" onClick={() => setEditingId(null)} className="text-xs text-zinc-500 hover:text-zinc-300">Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-zinc-200">{m.content}</p>
                  )}
                  <div className="mt-1.5 flex items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${CATEGORY_COLORS[m.category] || ''}`}>{m.category}</span>
                    <span className="text-[10px] text-zinc-600">{m.source}</span>
                    {m.relevance_score != null && (
                      <span className="text-[10px] text-blue-400">{Math.round(m.relevance_score * 100)}% match</span>
                    )}
                    <span className="text-[10px] text-zinc-700">{m.access_count} recalls</span>
                  </div>
                </div>
                <div className="flex shrink-0 gap-1 opacity-0 group-hover:opacity-100">
                  <button type="button" onClick={() => { setEditingId(m.id); setEditContent(m.content) }} className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300">
                    <span className="text-xs">Edit</span>
                  </button>
                  <button type="button" onClick={() => handleDelete(m.id)} className="rounded p-1 text-zinc-500 hover:bg-red-900/30 hover:text-red-400">
                    <span className="text-xs">Del</span>
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

## 8. Add the Memory tab in `frontend/src/components/settings/SettingsPage.tsx`

In the tabs array, add a new tab entry. Do not remove or reorder existing tabs:

```tsx
import { MemoryTab } from './MemoryTab'
```

Add to the tabs array (after existing tabs, before the last one):
```tsx
{ id: 'memory', label: 'Memory', component: <MemoryTab /> },
```

---

## Verification
1. `cd frontend && npm run build` — zero errors
2. `cd frontend && npm run lint` — zero errors
3. Backend starts without import errors
4. `POST /api/memory/` creates a memory with embedding
5. `GET /api/memory/` lists user memories
6. `GET /api/memory/search?q=...` returns semantically ranked results
7. `PUT /api/memory/{id}` updates content and re-generates embedding
8. `DELETE /api/memory/{id}` removes entry
9. `GET /api/memory/stats` returns correct counts
10. MemoryTab renders with add form, category filter, search, pin toggle, edit, delete
11. Settings page shows "Memory" tab
12. Hash fallback embedding works when no OpenAI key is present
