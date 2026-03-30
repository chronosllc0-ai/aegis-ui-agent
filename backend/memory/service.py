"""Memory CRUD and semantic retrieval service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func as sa_func, select, update
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
    ) -> dict[str, Any]:
        embedding = await get_embedding(content, api_key, embedding_provider)
        entry = MemoryEntry(
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
    ) -> list[dict[str, Any]]:
        query_embedding = await get_embedding(query, api_key, embedding_provider)
        stmt = select(MemoryEntry).where(MemoryEntry.user_id == user_id)
        if category:
            stmt = stmt.where(MemoryEntry.category == category)
        entries = (await session.execute(stmt)).scalars().all()

        scored: list[tuple[float, MemoryEntry]] = []
        for entry in entries:
            if entry.embedding:
                try:
                    emb = json.loads(entry.embedding)
                except Exception:
                    continue
                score = cosine_similarity(query_embedding, emb)
            else:
                score = 1.0 if query.lower() in entry.content.lower() else 0.0
            if score >= min_similarity:
                scored.append((score, entry))

        scored.sort(key=lambda s: (s[0], s[1].importance or 0.0, s[1].is_pinned), reverse=True)

        now = datetime.now(timezone.utc)
        results: list[dict[str, Any]] = []
        for score, entry in scored[:limit]:
            await session.execute(
                update(MemoryEntry)
                .where(MemoryEntry.id == entry.id)
                .values(access_count=(entry.access_count or 0) + 1, last_accessed_at=now)
            )
            d = _entry_to_dict(entry)
            d["relevance_score"] = score
            results.append(d)
        await session.commit()
        return results

    @staticmethod
    async def list_memories(
        session: AsyncSession,
        user_id: str,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(MemoryEntry)
            .where(MemoryEntry.user_id == user_id)
            .order_by(MemoryEntry.is_pinned.desc(), MemoryEntry.updated_at.desc(), MemoryEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if category:
            stmt = stmt.where(MemoryEntry.category == category)
        return [_entry_to_dict(e) for e in (await session.execute(stmt)).scalars().all()]

    @staticmethod
    async def get_memory(session: AsyncSession, memory_id: str, user_id: str) -> dict[str, Any] | None:
        entry = (
            await session.execute(
                select(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.user_id == user_id)
            )
        ).scalar_one_or_none()
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
    ) -> dict[str, Any] | None:
        entry = (
            await session.execute(
                select(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.user_id == user_id)
            )
        ).scalar_one_or_none()
        if not entry:
            return None

        if content is not None:
            entry.content = content
            emb = await get_embedding(content, api_key, embedding_provider)
            entry.embedding = json.dumps(emb)
            entry.embedding_model = f"{embedding_provider}/text-embedding-3-small" if api_key else "hash-fallback"
        if category is not None:
            entry.category = category
        if importance is not None:
            entry.importance = float(max(0.0, min(1.0, importance)))
        if is_pinned is not None:
            entry.is_pinned = bool(is_pinned)
        await session.commit()
        await session.refresh(entry)
        return _entry_to_dict(entry)

    @staticmethod
    async def delete_memory(session: AsyncSession, memory_id: str, user_id: str) -> bool:
        result = await session.execute(
            delete(MemoryEntry).where(MemoryEntry.id == memory_id, MemoryEntry.user_id == user_id)
        )
        await session.commit()
        return bool(result.rowcount)

    @staticmethod
    async def get_stats(session: AsyncSession, user_id: str) -> dict[str, Any]:
        total = (
            await session.execute(select(sa_func.count(MemoryEntry.id)).where(MemoryEntry.user_id == user_id))
        ).scalar() or 0
        pinned = (
            await session.execute(
                select(sa_func.count(MemoryEntry.id)).where(MemoryEntry.user_id == user_id, MemoryEntry.is_pinned.is_(True))
            )
        ).scalar() or 0
        rows = (
            await session.execute(
                select(MemoryEntry.category, sa_func.count(MemoryEntry.id))
                .where(MemoryEntry.user_id == user_id)
                .group_by(MemoryEntry.category)
            )
        ).all()
        return {
            "total_memories": int(total),
            "pinned_memories": int(pinned),
            "by_category": {str(cat or "general"): int(cnt) for cat, cnt in rows},
        }


def _entry_to_dict(entry: MemoryEntry) -> dict[str, Any]:
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
