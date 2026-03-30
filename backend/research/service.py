"""Deep research orchestration service."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.artifacts.service import ArtifactService
from backend.database import ResearchSession
from backend.research.web_search import SearchResult, web_search


class ResearchService:
    """Orchestrates deep research sessions."""

    @staticmethod
    async def start_research(
        session: AsyncSession,
        user_id: str,
        topic: str,
        api_key: str,
        provider_name: str = "google",
        model: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        research = ResearchSession(user_id=user_id, topic=topic, status="searching", conversation_id=conversation_id)
        session.add(research)
        await session.commit()
        await session.refresh(research)

        queries = [topic, f"{topic} statistics", f"{topic} latest trends", f"{topic} expert analysis", f"{topic} risks"]
        research.total_queries = len(queries)
        await session.commit()

        all_results: list[SearchResult] = []
        for query in queries:
            results = await web_search(query, num_results=6)
            all_results.extend(results)
            research.queries_completed = (research.queries_completed or 0) + 1
            research.total_sources = len({r.url for r in all_results})
            await session.commit()
            await asyncio.sleep(0)

        report_lines = [
            f"# Deep Research Report: {topic}",
            "",
            "## Executive Summary",
            f"This report summarizes findings for **{topic}**.",
            "",
            "## Key Findings",
        ]
        for i, result in enumerate(all_results[:25], start=1):
            report_lines.append(f"{i}. [{result.title}]({result.url}) — {result.snippet}")
        report_lines.extend(["", "## Sources"])
        for result in all_results[:50]:
            report_lines.append(f"- [{result.title}]({result.url})")

        report_content = "\n".join(report_lines)
        artifact = await ArtifactService.create(
            session,
            user_id=user_id,
            title=f"Research Report - {topic}",
            content=report_content,
            artifact_type="document",
            conversation_id=conversation_id,
            description="Automatically generated deep research report",
        )

        research.status = "completed"
        research.report_artifact_id = artifact["id"]
        research.completed_at = datetime.now(timezone.utc)
        research.research_plan = json.dumps({"queries": queries})
        research.findings_json = json.dumps([r.__dict__ for r in all_results[:200]])
        await session.commit()
        await session.refresh(research)
        return _session_to_dict(research)

    @staticmethod
    async def list_sessions(session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(ResearchSession).where(ResearchSession.user_id == user_id).order_by(ResearchSession.created_at.desc())
            )
        ).scalars().all()
        return [_session_to_dict(r) for r in rows]

    @staticmethod
    async def get_session(session: AsyncSession, research_id: str, user_id: str) -> dict[str, Any] | None:
        row = (
            await session.execute(
                select(ResearchSession).where(ResearchSession.id == research_id, ResearchSession.user_id == user_id)
            )
        ).scalar_one_or_none()
        return _session_to_dict(row) if row else None


def _session_to_dict(r: ResearchSession) -> dict[str, Any]:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "topic": r.topic,
        "status": r.status,
        "total_sources": r.total_sources,
        "total_queries": r.total_queries,
        "queries_completed": r.queries_completed,
        "report_artifact_id": r.report_artifact_id,
        "error_message": r.error_message,
        "tokens_used": r.tokens_used,
        "credits_used": r.credits_used,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }
