"""Deep research orchestration service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import ResearchSession
from backend.providers.base import ChatMessage
from backend.providers import get_provider
from backend.research.web_search import brave_search
from config import settings


class ResearchService:
    """Run and track deep research sessions."""

    @staticmethod
    async def start_research(
        session: AsyncSession,
        user_id: str,
        topic: str,
        api_key: str,
        provider_name: str = "google",
        model: str | None = None,
        conversation_id: str | None = None,
        on_progress=None,
    ) -> dict:
        research = ResearchSession(
            id=str(uuid4()),
            user_id=user_id,
            conversation_id=conversation_id,
            topic=topic,
            status="planning",
            started_at=datetime.now(timezone.utc),
        )
        session.add(research)
        await session.commit()
        await session.refresh(research)

        async def emit(phase: str, **extra) -> None:
            if on_progress:
                await on_progress({"phase": phase, **extra})

        await emit("planning")
        queries = [
            f"{topic} market overview",
            f"{topic} latest trends 2026",
            f"{topic} risks and opportunities",
        ]
        research.research_plan = json.dumps({"queries": queries})
        research.total_queries = len(queries)
        research.status = "searching"
        await session.commit()

        await emit("searching")
        results: list[dict] = []
        search_key = settings.BRAVE_SEARCH_API_KEY
        for idx, query in enumerate(queries, start=1):
            if search_key:
                items = await brave_search(query, search_key, count=6)
            else:
                items = []
            results.extend(items)
            research.queries_completed = idx
            await session.commit()

        research.sources_json = json.dumps(results)
        research.total_sources = len(results)
        research.status = "synthesizing"
        await session.commit()

        await emit("synthesizing")
        provider = get_provider(provider_name, api_key)
        model_name = model or (provider.available_models[0] if provider.available_models else None)
        snippets = "\n".join(f"- {r.get('title')}: {r.get('snippet')} ({r.get('url')})" for r in results[:20])
        prompt = (
            f"Create a structured research report on: {topic}\n"
            f"Use these source snippets:\n{snippets}\n"
            "Return markdown with sections: Executive Summary, Key Findings, Risks, Opportunities, Sources."
        )
        response = await provider.chat(
            [ChatMessage(role="system", content="You are a senior research analyst."), ChatMessage(role="user", content=prompt)],
            model=model_name,
            temperature=0.2,
            max_tokens=3000,
        )

        report = response.content.strip()
        research.findings_json = json.dumps({"report": report})
        research.status = "completed"
        research.completed_at = datetime.now(timezone.utc)
        await session.commit()
        await emit("completed")

        return _to_dict(research)

    @staticmethod
    async def list_sessions(session: AsyncSession, user_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
        result = await session.execute(
            select(ResearchSession)
            .where(ResearchSession.user_id == user_id)
            .order_by(ResearchSession.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_to_dict(r) for r in result.scalars().all()]

    @staticmethod
    async def get_session(session: AsyncSession, user_id: str, research_id: str) -> dict | None:
        result = await session.execute(
            select(ResearchSession).where(ResearchSession.id == research_id, ResearchSession.user_id == user_id)
        )
        entry = result.scalar_one_or_none()
        return _to_dict(entry) if entry else None


def _to_dict(r: ResearchSession) -> dict:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "conversation_id": r.conversation_id,
        "topic": r.topic,
        "status": r.status,
        "research_plan": json.loads(r.research_plan) if r.research_plan else None,
        "sources": json.loads(r.sources_json) if r.sources_json else [],
        "findings": json.loads(r.findings_json) if r.findings_json else None,
        "report_artifact_id": r.report_artifact_id,
        "total_sources": r.total_sources,
        "total_queries": r.total_queries,
        "queries_completed": r.queries_completed,
        "tokens_used": r.tokens_used,
        "credits_used": r.credits_used,
        "error_message": r.error_message,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }
