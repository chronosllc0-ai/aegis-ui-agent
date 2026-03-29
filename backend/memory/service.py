"""Memory CRUD and semantic retrieval service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import MemoryEntry
from backend.memory.embeddings import cosine_similarity, get_embedding


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
        query_embedding = await get_embedding(query, api_key, embedding_provider)
        stmt = select(MemoryEntry).where(MemoryEntry.user_id == user_id)
        if category:
            stmt = stmt.where(MemoryEntry.category == category)
        result = await session.execute(stmt)
        entries = result.scalars().all()
        scored: list[tuple[float, MemoryEntry]] = []
        for entry in entries:
            if not entry.embedding:
                continue
            sim = cosine_similarity(query_embedding, json.loads(entry.embedding))
            if sim >= min_similarity:
                scored.append((sim * (1.2 if entry.is_pinned else 1.0), entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]
        for _, entry in top:
            entry.access_count = (entry.access_count or 0) + 1
            entry.last_accessed_at = datetime.now(timezone.utc)
        await session.commit()
        return [{**_entry_to_dict(entry), "relevance_score": round(score, 4)} for score, entry in top]

    @staticmethod
    async def list_memories(
        session: AsyncSession,
        user_id: str,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        stmt = select(MemoryEntry).where(MemoryEntry.user_id == user_id)
        if category:
            stmt = stmt.where(MemoryEntry.category == category)
        stmt = stmt.order_by(MemoryEntry.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return [_entry_to_dict(e) for e in result.scalars().all()]

    @staticmethod
    async def get_memory(session: AsyncSession, memory_id: str, user_id: str) -> dict | None:
        result = await session.execute(select(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.user_id == user_id))
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
        result = await session.execute(select(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.user_id == user_id))
        entry = result.scalar_one_or_none()
        if not entry:
            return None
        if content is not None and content != entry.content:
            entry.content = content
            emb = await get_embedding(content, api_key, embedding_provider)
            entry.embedding = json.dumps(emb)
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
        result = await session.execute(delete(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.user_id == user_id))
        await session.commit()
        return bool(result.rowcount)

    @staticmethod
    async def get_stats(session: AsyncSession, user_id: str) -> dict:
        result = await session.execute(
            select(sa_func.count(MemoryEntry.id), sa_func.count(sa_func.nullif(MemoryEntry.is_pinned, False))).where(MemoryEntry.user_id == user_id)
        )
        total_count, pinned_count = result.one()
        cat_result = await session.execute(
            select(MemoryEntry.category, sa_func.count(MemoryEntry.id)).where(MemoryEntry.user_id == user_id).group_by(MemoryEntry.category)
        )
        return {
            "total_memories": total_count,
            "pinned_memories": pinned_count,
            "by_category": {cat: count for cat, count in cat_result.all()},
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
        memories = await MemoryService.recall(
            session,
            user_id,
            query,
            limit=max_memories,
            min_similarity=0.35,
            api_key=api_key,
            embedding_provider=embedding_provider,
        )
        if not memories:
            return ""
        lines = ["[User Memory Context]"]
        for memory in memories:
            pin_marker = " [pinned]" if memory.get("is_pinned") else ""
            lines.append(f"- ({memory['category']}{pin_marker}) {memory['content']}")
        lines.append("[End Memory Context]")
        return "\n".join(lines)


def _entry_to_dict(entry: MemoryEntry) -> dict:
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
