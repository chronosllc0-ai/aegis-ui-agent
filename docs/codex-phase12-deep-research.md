# Codex Phase 12: Deep Research Mode

## Project Context
Aegis is a FastAPI + React/TypeScript app. The task planner (Phase 7), sub-agent orchestration (Phase 8), and artifact system (Phase 11) handle complex multi-step tasks. However, there is no dedicated research mode that performs iterative web search, source extraction, fact synthesis, and citation tracking to produce a comprehensive research document.

This phase adds a Deep Research mode that:
1. Takes a research question or topic
2. Generates a research plan with search queries
3. Executes searches in parallel (using the connector system or a web search API)
4. Extracts and synthesizes findings with source attribution
5. Produces a structured research report with citations
6. Saves the report as an artifact

## What to implement
1. `backend/research/` module with research orchestrator, source extraction, and report generation
2. API endpoints for starting, monitoring, and retrieving research sessions
3. Database model for research sessions with status tracking
4. Frontend Deep Research trigger in the UI with a real-time progress panel
5. Integration with the web search capability (via `httpx` + search API)

## CRITICAL RULES
- Do NOT modify: `orchestrator.py`, `session.py`, `navigator.py`, `analyzer.py`, `executor.py`, `mcp_client.py`
- Do NOT modify: any existing file in `backend/providers/`, `backend/connectors/`, `backend/admin/`, `backend/planner/`, `backend/gallery/`, `backend/memory/`, `backend/artifacts/`
- Do NOT modify: `backend/credit_rates.py`, `backend/credit_service.py`, `backend/key_management.py`, `backend/conversation_service.py`
- Do NOT modify: any file in `frontend/src/components/settings/`
- Do NOT modify: `frontend/src/components/LandingPage.tsx`, `frontend/src/components/AuthPage.tsx`
- Do NOT modify: `auth.py`
- You MAY add models to `backend/database.py` and router registrations to `main.py`
- Research uses the provider system (`backend/providers/get_provider`) for all LLM calls
- Web search uses `httpx` with Brave Search API or SerpAPI (configurable via `SEARCH_API_KEY` and `SEARCH_PROVIDER` env vars, default Brave)
- ESLint strict: NO `setState` in `useEffect` bodies, NO ref access during render
- Tailwind v4 dark theme colors
- Use `apiUrl('/path')` for ALL frontend API calls

---

## Database Model

Add to `backend/database.py` AFTER existing models:

```python
class ResearchSession(Base):
    """A deep research session with iterative search and synthesis."""

    __tablename__ = "research_sessions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    conversation_id = Column(String(255), ForeignKey("conversations.id"), nullable=True)
    topic = Column(Text, nullable=False)
    status = Column(String(20), default="planning")  # planning | searching | synthesizing | completed | failed
    research_plan = Column(Text)  # JSON: list of search queries and subtopics
    sources_json = Column(Text)  # JSON: collected sources with metadata
    findings_json = Column(Text)  # JSON: extracted findings per source
    report_artifact_id = Column(String(255), nullable=True)  # FK to artifacts when report is generated
    total_sources = Column(Integer, default=0)
    total_queries = Column(Integer, default=0)
    queries_completed = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    credits_used = Column(Float, default=0.0)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
```

---

## 1. Create `backend/research/__init__.py`

```python
"""Deep research mode — iterative search, extraction, and synthesis."""

from .service import ResearchService

__all__ = ["ResearchService"]
```

## 2. Create `backend/research/web_search.py`

```python
"""Web search abstraction — supports Brave Search and SerpAPI."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from config import settings

logger = logging.getLogger(__name__)

SEARCH_PROVIDER = getattr(settings, "SEARCH_PROVIDER", "brave")
SEARCH_API_KEY = getattr(settings, "SEARCH_API_KEY", "")


@dataclass
class SearchResult:
    """A single web search result."""
    title: str
    url: str
    snippet: str
    source_name: str = ""
    published_date: str | None = None


async def web_search(query: str, num_results: int = 10) -> list[SearchResult]:
    """Perform a web search and return results.

    Uses Brave Search API by default. Falls back to SerpAPI if configured.
    Returns empty list if no API key is configured.
    """
    if not SEARCH_API_KEY:
        logger.warning("No SEARCH_API_KEY configured — web search disabled")
        return []

    if SEARCH_PROVIDER == "brave":
        return await _brave_search(query, num_results)
    elif SEARCH_PROVIDER == "serpapi":
        return await _serpapi_search(query, num_results)
    else:
        logger.warning("Unknown search provider: %s", SEARCH_PROVIDER)
        return []


async def _brave_search(query: str, num_results: int = 10) -> list[SearchResult]:
    """Search using Brave Search API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": SEARCH_API_KEY, "Accept": "application/json"},
                params={"q": query, "count": num_results},
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("web", {}).get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
                source_name=item.get("meta_url", {}).get("hostname", ""),
                published_date=item.get("age"),
            ))
        return results
    except Exception:
        logger.warning("Brave search failed", exc_info=True)
        return []


async def _serpapi_search(query: str, num_results: int = 10) -> list[SearchResult]:
    """Search using SerpAPI."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://serpapi.com/search",
                params={"q": query, "api_key": SEARCH_API_KEY, "num": num_results, "engine": "google"},
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("organic_results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                source_name=item.get("displayed_link", ""),
                published_date=item.get("date"),
            ))
        return results
    except Exception:
        logger.warning("SerpAPI search failed", exc_info=True)
        return []
```

## 3. Create `backend/research/service.py`

```python
"""Deep research orchestration service.

Manages the research lifecycle:
1. Plan — generate search queries from the topic
2. Search — execute queries in parallel
3. Extract — pull key findings from each source
4. Synthesize — combine findings into a structured report
5. Deliver — save report as an artifact
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any, Callable, Awaitable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import ResearchSession, _session_factory
from backend.providers import get_provider
from backend.providers.base import ChatMessage
from backend.research.web_search import web_search, SearchResult

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]

PLAN_SYSTEM_PROMPT = """You are a research planning engine. Given a research topic, generate a list of search queries that will comprehensively cover the topic.

Rules:
- Generate 5-15 search queries
- Cover different angles and subtopics
- Include queries for data, statistics, expert opinions, recent developments
- Return ONLY valid JSON in this format:

{
  "title": "Research title",
  "subtopics": ["subtopic1", "subtopic2"],
  "queries": [
    {"query": "search query text", "purpose": "what this query should find"}
  ]
}"""

EXTRACT_SYSTEM_PROMPT = """You are a research extraction engine. Given search results for a query, extract key findings, facts, and quotes.

Return ONLY valid JSON:
{
  "findings": [
    {
      "fact": "The key finding or fact",
      "source_url": "URL where this was found",
      "confidence": "high|medium|low",
      "category": "statistic|opinion|fact|trend|definition"
    }
  ]
}"""

SYNTHESIS_SYSTEM_PROMPT = """You are a research report writer. Given a collection of research findings from multiple sources, write a comprehensive, well-structured research report.

Rules:
- Use markdown formatting with headers, bullets, and emphasis
- Include inline citations as [Source Title](URL)
- Start with an executive summary
- Organize by themes/subtopics
- Include a "Key Findings" section with numbered points
- End with a "Sources" section listing all referenced URLs
- Be thorough but concise — aim for 2000-4000 words
- Note any conflicting information between sources
- Distinguish between facts, opinions, and projections"""


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
        on_progress: ProgressCallback | None = None,
    ) -> dict:
        """Start a deep research session. Runs the full pipeline."""
        research_id = str(uuid4())

        research = ResearchSession(
            id=research_id,
            user_id=user_id,
            conversation_id=conversation_id,
            topic=topic,
            status="planning",
        )
        session.add(research)
        await session.commit()

        try:
            # Phase 1: Generate research plan
            if on_progress:
                await on_progress({"type": "phase", "phase": "planning", "research_id": research_id})

            provider = get_provider(provider_name, api_key)
            plan = await ResearchService._generate_plan(provider, topic, model)

            research.research_plan = json.dumps(plan)
            research.total_queries = len(plan.get("queries", []))
            research.status = "searching"
            await session.commit()

            if on_progress:
                await on_progress({"type": "plan_ready", "queries": len(plan.get("queries", [])), "subtopics": plan.get("subtopics", [])})

            # Phase 2: Execute searches in parallel
            queries = plan.get("queries", [])
            all_results: list[tuple[str, list[SearchResult]]] = []

            semaphore = asyncio.Semaphore(3)  # Max 3 concurrent searches

            async def search_one(q: dict) -> tuple[str, list[SearchResult]]:
                async with semaphore:
                    results = await web_search(q["query"], num_results=8)
                    research.queries_completed = (research.queries_completed or 0) + 1
                    await session.commit()
                    if on_progress:
                        await on_progress({
                            "type": "search_done",
                            "query": q["query"],
                            "results_count": len(results),
                            "progress": f"{research.queries_completed}/{research.total_queries}",
                        })
                    return q["query"], results

            search_tasks = [search_one(q) for q in queries]
            all_results = await asyncio.gather(*search_tasks, return_exceptions=True)

            # Collect valid results
            sources: list[dict] = []
            for item in all_results:
                if isinstance(item, tuple):
                    query_text, results = item
                    for r in results:
                        sources.append({
                            "query": query_text,
                            "title": r.title,
                            "url": r.url,
                            "snippet": r.snippet,
                            "source_name": r.source_name,
                        })

            # Deduplicate by URL
            seen_urls: set[str] = set()
            unique_sources: list[dict] = []
            for s in sources:
                if s["url"] not in seen_urls:
                    seen_urls.add(s["url"])
                    unique_sources.append(s)

            research.sources_json = json.dumps(unique_sources)
            research.total_sources = len(unique_sources)
            research.status = "synthesizing"
            await session.commit()

            if on_progress:
                await on_progress({"type": "phase", "phase": "extracting", "total_sources": len(unique_sources)})

            # Phase 3: Extract findings
            findings = await ResearchService._extract_findings(provider, unique_sources, topic, model)
            research.findings_json = json.dumps(findings)
            await session.commit()

            if on_progress:
                await on_progress({"type": "phase", "phase": "synthesizing", "total_findings": len(findings)})

            # Phase 4: Synthesize report
            report = await ResearchService._synthesize_report(provider, topic, findings, unique_sources, model)

            # Phase 5: Save as artifact
            from backend.artifacts.service import ArtifactService
            artifact = await ArtifactService.create(
                session, user_id,
                title=f"Research: {plan.get('title', topic[:100])}",
                content=report,
                artifact_type="document",
                filename=f"research-{research_id[:8]}.md",
                description=f"Deep research report on: {topic[:200]}",
                conversation_id=conversation_id,
            )

            research.report_artifact_id = artifact["id"]
            research.status = "completed"
            research.completed_at = datetime.now(timezone.utc)
            await session.commit()

            if on_progress:
                await on_progress({"type": "completed", "artifact_id": artifact["id"], "report_preview": report[:500]})

            return _research_to_dict(research)

        except Exception as exc:
            research.status = "failed"
            research.error_message = str(exc)
            await session.commit()
            logger.exception("Research failed for %s", research_id)
            if on_progress:
                await on_progress({"type": "failed", "error": str(exc)})
            return _research_to_dict(research)

    @staticmethod
    async def _generate_plan(provider: Any, topic: str, model: str | None) -> dict:
        """Use LLM to generate a research plan."""
        messages = [
            ChatMessage(role="system", content=PLAN_SYSTEM_PROMPT),
            ChatMessage(role="user", content=f"Research topic: {topic}"),
        ]
        response = await provider.chat(messages, model=model, temperature=0.4, max_tokens=2048)
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3].strip()
        return json.loads(content)

    @staticmethod
    async def _extract_findings(
        provider: Any,
        sources: list[dict],
        topic: str,
        model: str | None,
    ) -> list[dict]:
        """Extract key findings from search results in batches."""
        all_findings: list[dict] = []

        # Process in batches of 10 sources
        batch_size = 10
        for i in range(0, len(sources), batch_size):
            batch = sources[i:i + batch_size]
            source_text = "\n\n".join(
                f"Source: {s['title']} ({s['url']})\nSnippet: {s['snippet']}"
                for s in batch
            )

            messages = [
                ChatMessage(role="system", content=EXTRACT_SYSTEM_PROMPT),
                ChatMessage(role="user", content=f"Topic: {topic}\n\nSearch Results:\n{source_text}"),
            ]
            response = await provider.chat(messages, model=model, temperature=0.3, max_tokens=3000)
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                if content.endswith("```"):
                    content = content[:-3].strip()
            try:
                parsed = json.loads(content)
                all_findings.extend(parsed.get("findings", []))
            except json.JSONDecodeError:
                logger.warning("Failed to parse extraction response")

        return all_findings

    @staticmethod
    async def _synthesize_report(
        provider: Any,
        topic: str,
        findings: list[dict],
        sources: list[dict],
        model: str | None,
    ) -> str:
        """Synthesize a research report from findings."""
        findings_text = "\n".join(
            f"- [{f.get('category', 'fact')}] {f['fact']} (confidence: {f.get('confidence', 'medium')}, source: {f.get('source_url', 'unknown')})"
            for f in findings
        )

        sources_text = "\n".join(
            f"- {s['title']}: {s['url']}"
            for s in sources[:50]  # Limit to avoid context overflow
        )

        messages = [
            ChatMessage(role="system", content=SYNTHESIS_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=f"Research Topic: {topic}\n\n## Collected Findings ({len(findings)} total):\n{findings_text}\n\n## Available Sources ({len(sources)} total):\n{sources_text}",
            ),
        ]
        response = await provider.chat(messages, model=model, temperature=0.5, max_tokens=8192)
        return response.content

    @staticmethod
    async def get_session(session: AsyncSession, research_id: str, user_id: str) -> dict | None:
        """Get a research session."""
        result = await session.execute(
            select(ResearchSession).where(ResearchSession.id == research_id, ResearchSession.user_id == user_id)
        )
        r = result.scalar_one_or_none()
        return _research_to_dict(r) if r else None

    @staticmethod
    async def list_sessions(session: AsyncSession, user_id: str, limit: int = 20) -> list[dict]:
        """List user's research sessions."""
        result = await session.execute(
            select(ResearchSession)
            .where(ResearchSession.user_id == user_id)
            .order_by(ResearchSession.created_at.desc())
            .limit(limit)
        )
        return [_research_to_dict(r) for r in result.scalars().all()]


def _research_to_dict(r: ResearchSession) -> dict:
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
```

## 4. Create `backend/research/router.py`

```python
"""API routes for deep research sessions."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import get_session
from backend.key_management import KeyManager
from backend.research.service import ResearchService
from config import settings

logger = logging.getLogger(__name__)
research_router = APIRouter(prefix="/api/research", tags=["research"])
key_manager = KeyManager(settings.ENCRYPTION_SECRET)


def _get_user_uid(request) -> str:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload["uid"]


@research_router.post("/start")
async def start_research(
    payload: dict[str, Any],
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start a deep research session. Returns immediately with the session ID.

    Body: { "topic": "...", "provider": "google", "model": "gemini-2.5-pro", "conversation_id": "..." }
    """
    uid = _get_user_uid(request)
    topic = payload.get("topic", "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    provider_name = payload.get("provider", "google")
    model = payload.get("model")

    api_key = await key_manager.get_key(db, uid, provider_name)
    if not api_key:
        fallback = {
            "google": settings.GEMINI_API_KEY,
            "openai": getattr(settings, "OPENAI_API_KEY", ""),
            "anthropic": getattr(settings, "ANTHROPIC_API_KEY", ""),
        }
        api_key = fallback.get(provider_name, "")
    if not api_key:
        raise HTTPException(status_code=400, detail=f"No API key for {provider_name}")

    # Start research in background
    async def run():
        from backend.database import _session_factory
        if _session_factory:
            async with _session_factory() as new_db:
                await ResearchService.start_research(
                    new_db, uid, topic, api_key,
                    provider_name=provider_name,
                    model=model,
                    conversation_id=payload.get("conversation_id"),
                )

    asyncio.create_task(run())

    return {"ok": True, "message": "Research started"}


@research_router.get("/")
async def list_research_sessions(
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List user's research sessions."""
    uid = _get_user_uid(request)
    sessions = await ResearchService.list_sessions(db, uid)
    return {"ok": True, "sessions": sessions}


@research_router.get("/{research_id}")
async def get_research_session(
    research_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a research session with status."""
    uid = _get_user_uid(request)
    res = await ResearchService.get_session(db, research_id, uid)
    if not res:
        raise HTTPException(status_code=404, detail="Research session not found")
    return {"ok": True, "session": res}
```

## 5. Register router in `main.py`

Add import:
```python
from backend.research.router import research_router
```

Add registration:
```python
app.include_router(research_router)
```

Also add to `config.py` Settings class:
```python
SEARCH_API_KEY: str = ""
SEARCH_PROVIDER: str = "brave"  # "brave" or "serpapi"
```

## 6. Create `frontend/src/components/DeepResearch.tsx`

```tsx
import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../lib/api'

type ResearchSession = {
  id: string
  topic: string
  status: 'planning' | 'searching' | 'synthesizing' | 'completed' | 'failed'
  total_sources: number
  total_queries: number
  queries_completed: number
  report_artifact_id: string | null
  error_message: string | null
  created_at: string | null
  completed_at: string | null
}

type DeepResearchProps = {
  onArtifactReady?: (artifactId: string) => void
}

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  planning: { label: 'Generating research plan...', color: 'text-blue-400' },
  searching: { label: 'Searching the web...', color: 'text-blue-400' },
  synthesizing: { label: 'Synthesizing findings...', color: 'text-purple-400' },
  completed: { label: 'Research complete', color: 'text-emerald-400' },
  failed: { label: 'Research failed', color: 'text-red-400' },
}

export function DeepResearch({ onArtifactReady }: DeepResearchProps) {
  const [topic, setTopic] = useState('')
  const [sessions, setSessions] = useState<ResearchSession[]>([])
  const [activeSession, setActiveSession] = useState<ResearchSession | null>(null)
  const [starting, setStarting] = useState(false)

  const fetchSessions = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/research/'), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setSessions(data.sessions)
    } catch { /* silent */ }
  }, [])

  const pollSession = useCallback(async (id: string) => {
    try {
      const resp = await fetch(apiUrl(`/api/research/${id}`), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setActiveSession(data.session)
        if (data.session.status === 'completed' && data.session.report_artifact_id && onArtifactReady) {
          onArtifactReady(data.session.report_artifact_id)
        }
      }
    } catch { /* silent */ }
  }, [onArtifactReady])

  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  // Poll active session
  useEffect(() => {
    if (!activeSession || ['completed', 'failed'].includes(activeSession.status)) return
    const interval = setInterval(() => pollSession(activeSession.id), 3000)
    return () => clearInterval(interval)
  }, [activeSession, pollSession])

  const handleStart = async () => {
    if (!topic.trim()) return
    setStarting(true)
    try {
      const resp = await fetch(apiUrl('/api/research/start'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic }),
      })
      const data = await resp.json()
      if (data.ok) {
        setTopic('')
        await fetchSessions()
      }
    } catch { /* silent */ } finally {
      setStarting(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Input */}
      <div className="rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-4">
        <h3 className="mb-2 text-sm font-semibold text-white">Deep Research</h3>
        <p className="mb-3 text-xs text-zinc-500">
          Enter a research topic. Aegis will search the web, extract findings, and synthesize a comprehensive report.
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleStart()}
            placeholder="e.g., Current state of AI agent frameworks in 2026"
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={handleStart}
            disabled={starting || !topic.trim()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {starting ? 'Starting...' : 'Research'}
          </button>
        </div>
      </div>

      {/* Active session progress */}
      {activeSession && !['completed', 'failed'].includes(activeSession.status) && (
        <div className="rounded-xl border border-blue-900/50 bg-blue-900/10 p-4">
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
            <span className={`text-xs font-medium ${STATUS_LABELS[activeSession.status]?.color || ''}`}>
              {STATUS_LABELS[activeSession.status]?.label}
            </span>
          </div>
          <p className="mt-1 text-xs text-zinc-400 truncate">{activeSession.topic}</p>
          {activeSession.total_queries > 0 && (
            <div className="mt-2">
              <div className="h-1.5 rounded-full bg-zinc-800">
                <div
                  className="h-1.5 rounded-full bg-blue-500 transition-all"
                  style={{ width: `${(activeSession.queries_completed / activeSession.total_queries) * 100}%` }}
                />
              </div>
              <span className="mt-1 text-[10px] text-zinc-600">
                {activeSession.queries_completed}/{activeSession.total_queries} queries · {activeSession.total_sources} sources
              </span>
            </div>
          )}
        </div>
      )}

      {/* Past sessions */}
      {sessions.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">Past Research</h4>
          <div className="space-y-1.5">
            {sessions.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setActiveSession(s)}
                className="flex w-full items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2 text-left hover:border-zinc-700"
              >
                <span className={`text-xs ${STATUS_LABELS[s.status]?.color || ''}`}>
                  {s.status === 'completed' ? '✓' : s.status === 'failed' ? '✗' : '◉'}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs text-zinc-200">{s.topic}</p>
                  <p className="text-[10px] text-zinc-600">{s.total_sources} sources · {s.created_at ? new Date(s.created_at).toLocaleDateString() : ''}</p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

---

## Verification
1. `cd frontend && npm run build` — zero errors
2. `cd frontend && npm run lint` — zero errors
3. Backend starts without import errors
4. `POST /api/research/start` begins a research session
5. `GET /api/research/` lists user sessions
6. `GET /api/research/{id}` shows status with progress
7. Research plan generates 5-15 queries
8. Web search returns results (when API key configured)
9. Findings are extracted and synthesized into a report
10. Report is saved as an artifact
11. DeepResearch component shows progress and links to completed reports
