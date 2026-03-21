# Codex Phase 9: Prompt Gallery & Suggestion Chips

## Project Context
Aegis is a FastAPI + React/TypeScript app. Frontend at `frontend/` uses Vite + React + TypeScript + Tailwind v4. The backend has task planning (Phase 7) and execution (Phase 8). There is a `workflowTemplates` array in the settings but no browseable prompt gallery. The `InputBar.tsx` has an `examplePrompt` prop but no suggestion chips. This phase adds a curated prompt gallery and suggestion chips for quick-start workflows.

## What to implement
Create a backend service for prompt templates with seeded data, API endpoints for browsing/filtering, a frontend gallery view with category tabs, and suggestion chips below the main input bar.

## CRITICAL RULES
- Do NOT modify: `orchestrator.py`, `session.py`, `navigator.py`, `analyzer.py`, `executor.py`, `mcp_client.py`
- Do NOT modify: any existing file in `backend/providers/`, `backend/connectors/`, `backend/admin/`, `backend/planner/`
- Do NOT modify: `frontend/src/components/settings/`, `frontend/src/components/LandingPage.tsx`, `frontend/src/components/AuthPage.tsx`
- Do NOT modify: `frontend/src/components/TaskPlanView.tsx`, `frontend/src/components/AgentActivityFeed.tsx`
- Do NOT modify: `auth.py`, `backend/database.py` (this phase uses no new database tables — templates are JSON-seeded)
- You MAY add new elements to `frontend/src/components/InputBar.tsx` — specifically a suggestion chips row ABOVE the input area. Do NOT change the existing InputBar logic, props, or styling.
- Use `apiUrl('/path')` for ALL API calls
- ESLint strict: NO `setState` in `useEffect` bodies, NO ref access during render
- Tailwind v4 dark theme: `bg-[#111]`, `bg-[#1a1a1a]`, `border-[#2a2a2a]`, `text-zinc-*`

---

## 1. Create `backend/gallery/__init__.py`

```python
"""Prompt gallery — curated workflow templates."""

from .service import GalleryService

__all__ = ["GalleryService"]
```

## 2. Create `backend/gallery/templates.json`

Seed file containing 25+ curated prompt templates. Each template has:
- `id`: unique slug
- `title`: short display title
- `description`: 1-2 sentence description
- `category`: one of "Research", "Sales", "Marketing", "Engineering", "Design", "Finance", "Productivity", "Content"
- `tags`: list of tag strings
- `prompt`: the full prompt text
- `required_connectors`: list of connector IDs needed (empty if none)
- `expected_artifacts`: list of expected output types ("document", "spreadsheet", "presentation", "dashboard", "report")
- `complexity`: "simple" | "moderate" | "complex"
- `estimated_credits`: approximate credit cost

```json
[
  {
    "id": "competitor-battlecards",
    "title": "Competitive Battle Cards",
    "description": "Research your top competitors and build a battle card for each with strengths, weaknesses, and positioning.",
    "category": "Sales",
    "tags": ["competitive intelligence", "sales enablement", "research"],
    "prompt": "Research my top 10 competitors in [industry]. For each competitor, find their: website, product offerings, pricing model, key differentiators, recent funding/news, social media presence, and customer sentiment. Build a competitive battle card for each with strengths, weaknesses, and suggested counter-positioning. Package everything into a slide deck.",
    "required_connectors": [],
    "expected_artifacts": ["presentation", "document"],
    "complexity": "complex",
    "estimated_credits": 150
  },
  {
    "id": "market-research-report",
    "title": "Market Research Report",
    "description": "Deep-dive market analysis with TAM/SAM/SOM, trends, and key players.",
    "category": "Research",
    "tags": ["market analysis", "TAM", "industry research"],
    "prompt": "Conduct a comprehensive market research report for [market/industry]. Include: market size (TAM, SAM, SOM), growth rate and projections, key trends and drivers, major players and market share, regulatory landscape, customer segments, and investment activity. Format as a structured report with executive summary.",
    "required_connectors": [],
    "expected_artifacts": ["document", "report"],
    "complexity": "complex",
    "estimated_credits": 120
  },
  {
    "id": "weekly-newsletter",
    "title": "Weekly Newsletter Draft",
    "description": "Research trending topics in your niche and draft a newsletter with curated insights.",
    "category": "Content",
    "tags": ["newsletter", "content creation", "curation"],
    "prompt": "Research the top trending topics in [niche/industry] from the past week. Curate the 5 most important stories with a brief analysis of each. Draft a newsletter that includes: attention-grabbing subject line, brief intro, the 5 curated stories with commentary, and a call-to-action. Tone: professional but conversational.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "moderate",
    "estimated_credits": 60
  },
  {
    "id": "code-review-checklist",
    "title": "Code Review Checklist",
    "description": "Generate a comprehensive code review checklist tailored to your tech stack.",
    "category": "Engineering",
    "tags": ["code review", "best practices", "engineering"],
    "prompt": "Create a comprehensive code review checklist for a [language/framework] project. Cover: code quality (naming, structure, DRY), security (input validation, auth, SQL injection), performance (N+1 queries, caching, memory), testing (coverage, edge cases, mocking), documentation (comments, API docs), and deployment readiness. Format as a markdown checklist.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "simple",
    "estimated_credits": 20
  },
  {
    "id": "social-media-calendar",
    "title": "30-Day Social Media Calendar",
    "description": "Plan a month of social media posts across platforms with copy and timing.",
    "category": "Marketing",
    "tags": ["social media", "content calendar", "planning"],
    "prompt": "Create a 30-day social media content calendar for [brand/product]. Include posts for Twitter/X, LinkedIn, and Instagram. For each post: date, platform, post type (text, image, video, carousel), copy/caption, suggested hashtags, optimal posting time, and content theme. Include a mix of educational, promotional, engagement, and behind-the-scenes content.",
    "required_connectors": [],
    "expected_artifacts": ["spreadsheet", "document"],
    "complexity": "moderate",
    "estimated_credits": 80
  },
  {
    "id": "financial-model",
    "title": "SaaS Financial Model",
    "description": "Build a 3-year financial projection model with revenue, costs, and key metrics.",
    "category": "Finance",
    "tags": ["financial modeling", "SaaS", "projections"],
    "prompt": "Build a 3-year SaaS financial model for [company]. Include: revenue projections (MRR, ARR, churn, expansion), cost structure (COGS, S&M, R&D, G&A), key metrics (CAC, LTV, LTV/CAC, payback period, burn rate, runway), unit economics, and break-even analysis. Assumptions should be clearly stated and adjustable.",
    "required_connectors": [],
    "expected_artifacts": ["spreadsheet", "document"],
    "complexity": "complex",
    "estimated_credits": 100
  },
  {
    "id": "design-system-tokens",
    "title": "Design System Tokens",
    "description": "Generate a complete design token system with colors, typography, spacing, and components.",
    "category": "Design",
    "tags": ["design system", "tokens", "UI"],
    "prompt": "Create a complete design token system for a modern SaaS product. Include: color palette (primary, secondary, neutral, semantic, dark/light mode), typography scale (font families, sizes, weights, line heights), spacing scale (4px base), border radii, shadow levels, breakpoints, and z-index layers. Output as a JSON token file and a visual reference document.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "moderate",
    "estimated_credits": 40
  },
  {
    "id": "onboarding-flow",
    "title": "User Onboarding Flow",
    "description": "Design a step-by-step onboarding experience with copy, triggers, and success metrics.",
    "category": "Productivity",
    "tags": ["onboarding", "UX", "activation"],
    "prompt": "Design a complete user onboarding flow for [product]. Include: welcome screen copy, step-by-step setup wizard (3-5 steps), progress indicator design, tooltip/coach mark sequences, empty state designs with CTAs, activation milestones, email sequence (welcome + 3 follow-ups), and success metrics to track. Focus on time-to-value.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "moderate",
    "estimated_credits": 50
  },
  {
    "id": "api-documentation",
    "title": "API Documentation",
    "description": "Generate comprehensive API docs from endpoint descriptions with examples.",
    "category": "Engineering",
    "tags": ["API", "documentation", "developer"],
    "prompt": "Generate comprehensive API documentation for [API name]. For each endpoint include: HTTP method and path, description, authentication requirements, request headers, request body schema with types, response schema with examples, error codes and messages, rate limits, and curl example. Include an overview section with base URL, authentication guide, and pagination pattern.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "moderate",
    "estimated_credits": 50
  },
  {
    "id": "pitch-deck",
    "title": "Investor Pitch Deck",
    "description": "Create a 12-slide pitch deck covering problem, solution, market, traction, and ask.",
    "category": "Sales",
    "tags": ["pitch deck", "fundraising", "investors"],
    "prompt": "Create a 12-slide investor pitch deck for [company]. Slides: 1) Title/hook, 2) Problem, 3) Solution, 4) Demo/Product, 5) Market size (TAM/SAM/SOM), 6) Business model, 7) Traction/metrics, 8) Competition, 9) Go-to-market strategy, 10) Team, 11) Financials/projections, 12) The Ask. For each slide: title, key bullet points, suggested visual/chart, and speaker notes.",
    "required_connectors": [],
    "expected_artifacts": ["presentation", "document"],
    "complexity": "complex",
    "estimated_credits": 100
  },
  {
    "id": "seo-audit",
    "title": "SEO Content Audit",
    "description": "Audit your website content for SEO opportunities with actionable recommendations.",
    "category": "Marketing",
    "tags": ["SEO", "content audit", "organic traffic"],
    "prompt": "Conduct an SEO content audit for [website URL]. Analyze: current keyword rankings, content gaps vs competitors, title tag and meta description optimization opportunities, internal linking structure, content freshness scores, thin content pages, duplicate content issues, and schema markup opportunities. Provide a prioritized action plan with estimated traffic impact.",
    "required_connectors": [],
    "expected_artifacts": ["document", "spreadsheet"],
    "complexity": "complex",
    "estimated_credits": 90
  },
  {
    "id": "email-sequence",
    "title": "Email Drip Campaign",
    "description": "Design a multi-step email sequence with subject lines, copy, and timing.",
    "category": "Marketing",
    "tags": ["email marketing", "drip campaign", "automation"],
    "prompt": "Create a 7-email drip campaign for [product/goal]. For each email: send timing (day after trigger), subject line (+ A/B variant), preview text, full email copy, CTA button text, and segmentation rules. Include: welcome email, value proposition, social proof, feature highlight, objection handling, urgency/scarcity, and final push. Track metrics: open rate targets, click targets, conversion goals.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "moderate",
    "estimated_credits": 60
  },
  {
    "id": "sprint-planning",
    "title": "Sprint Planning Template",
    "description": "Break down a project into sprint-ready user stories with estimates.",
    "category": "Engineering",
    "tags": ["agile", "sprint planning", "user stories"],
    "prompt": "Break down [project/feature] into sprint-ready user stories. For each story: title, description (As a [user], I want [action], so that [benefit]), acceptance criteria (Given/When/Then), story points estimate (Fibonacci), dependencies, and suggested assignee type (frontend, backend, design, QA). Group into 2-week sprints with a recommended order. Include technical spike stories where needed.",
    "required_connectors": [],
    "expected_artifacts": ["document", "spreadsheet"],
    "complexity": "moderate",
    "estimated_credits": 50
  },
  {
    "id": "brand-voice-guide",
    "title": "Brand Voice Guide",
    "description": "Define your brand's voice, tone, and messaging guidelines.",
    "category": "Content",
    "tags": ["brand voice", "style guide", "messaging"],
    "prompt": "Create a comprehensive brand voice guide for [brand]. Include: brand personality traits (3-5 adjectives), voice characteristics (what we sound like vs don't), tone spectrum (formal to casual with examples), vocabulary (preferred terms, words to avoid), grammar preferences, formatting rules, channel-specific guidelines (website, social, email, support), and 10 before/after copy examples showing the voice in action.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "moderate",
    "estimated_credits": 45
  },
  {
    "id": "incident-postmortem",
    "title": "Incident Post-Mortem",
    "description": "Structure a blameless post-mortem report from incident details.",
    "category": "Engineering",
    "tags": ["incident management", "post-mortem", "SRE"],
    "prompt": "Create a blameless post-mortem report for [incident description]. Include: incident summary, timeline of events (detection through resolution), root cause analysis (5 Whys), impact assessment (users affected, revenue impact, SLA breach), what went well, what went wrong, action items (with owners and due dates), detection improvements, and prevention measures. Follow Google SRE post-mortem format.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "simple",
    "estimated_credits": 30
  },
  {
    "id": "customer-persona",
    "title": "Customer Personas",
    "description": "Research and build detailed customer personas with demographics, goals, and pain points.",
    "category": "Research",
    "tags": ["personas", "customer research", "UX"],
    "prompt": "Create 4 detailed customer personas for [product/market]. For each persona: name, photo description, demographics (age, role, company size, industry), background story, goals (professional and personal), pain points and frustrations, preferred tools and channels, buying behavior, objections to our product, and a day-in-the-life scenario. Include a comparison matrix at the end.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "moderate",
    "estimated_credits": 55
  },
  {
    "id": "database-schema",
    "title": "Database Schema Design",
    "description": "Design a normalized database schema with tables, relationships, and indexes.",
    "category": "Engineering",
    "tags": ["database", "schema design", "SQL"],
    "prompt": "Design a database schema for [application type]. Include: entity-relationship diagram description, table definitions (columns, types, constraints), primary and foreign keys, indexes for common queries, normalization decisions (and where to denormalize), migration scripts (PostgreSQL), seed data examples, and query examples for the 5 most common operations. Consider: soft deletes, audit trails, multi-tenancy if applicable.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "moderate",
    "estimated_credits": 45
  },
  {
    "id": "pricing-strategy",
    "title": "Pricing Strategy Analysis",
    "description": "Analyze competitors and recommend a pricing model with tiers.",
    "category": "Finance",
    "tags": ["pricing", "strategy", "competitive analysis"],
    "prompt": "Develop a pricing strategy for [product]. Research: competitor pricing (at least 5 competitors), pricing models in the industry (per-seat, usage-based, flat-rate, hybrid), willingness-to-pay analysis framework. Recommend: pricing model, 3-4 tier structure with features per tier, free tier strategy, annual vs monthly discount, and enterprise pricing approach. Include a pricing page wireframe description.",
    "required_connectors": [],
    "expected_artifacts": ["document", "spreadsheet"],
    "complexity": "complex",
    "estimated_credits": 85
  },
  {
    "id": "weekly-standup-summary",
    "title": "Weekly Team Summary",
    "description": "Compile a team status report from standup notes and project updates.",
    "category": "Productivity",
    "tags": ["standup", "team management", "reporting"],
    "prompt": "Generate a weekly team summary report. For each team member, summarize: what they accomplished this week, what they're working on next week, blockers or risks, and key decisions made. Include: overall project health (green/yellow/red), sprint progress (% complete), upcoming milestones, and items needing leadership attention. Format for a 5-minute executive read.",
    "required_connectors": ["slack", "linear"],
    "expected_artifacts": ["document"],
    "complexity": "moderate",
    "estimated_credits": 40
  },
  {
    "id": "landing-page-copy",
    "title": "Landing Page Copy",
    "description": "Write conversion-optimized copy for a product landing page.",
    "category": "Content",
    "tags": ["copywriting", "landing page", "conversion"],
    "prompt": "Write conversion-optimized copy for a [product] landing page. Include: hero headline (3 variants for A/B testing), subheadline, 3 feature blocks with headlines and descriptions, social proof section (testimonial placeholders), pricing section copy, FAQ section (8 questions), CTA button text (3 variants), footer copy, and meta title + description for SEO. Tone: [specified tone].",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "simple",
    "estimated_credits": 35
  },
  {
    "id": "security-audit-checklist",
    "title": "Security Audit Checklist",
    "description": "Generate a comprehensive security review checklist for your application.",
    "category": "Engineering",
    "tags": ["security", "audit", "compliance"],
    "prompt": "Create a security audit checklist for a [web app/API/mobile app]. Cover: authentication (OAuth, MFA, session management), authorization (RBAC, resource-level), data protection (encryption at rest/transit, PII handling), input validation (XSS, SQLi, CSRF), API security (rate limiting, API keys, CORS), infrastructure (secrets management, logging, monitoring), dependency security (CVE scanning), and compliance (GDPR, SOC2, HIPAA as applicable). Prioritize by severity.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "moderate",
    "estimated_credits": 40
  },
  {
    "id": "content-repurposing",
    "title": "Content Repurposing Plan",
    "description": "Transform a blog post or video into 10+ pieces of content across platforms.",
    "category": "Content",
    "tags": ["content repurposing", "cross-platform", "distribution"],
    "prompt": "Take [blog post/video URL or topic] and create a content repurposing plan. Generate: 5 Twitter/X thread ideas with hooks, 3 LinkedIn posts (different angles), 2 Instagram carousel outlines (slides), 1 YouTube Shorts/TikTok script, 1 newsletter edition, 3 quote graphics text, and 1 podcast talking points outline. Each piece should have platform-specific formatting and hooks.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "moderate",
    "estimated_credits": 55
  },
  {
    "id": "data-pipeline-design",
    "title": "Data Pipeline Architecture",
    "description": "Design an ETL/ELT pipeline with source mapping, transformations, and scheduling.",
    "category": "Engineering",
    "tags": ["data engineering", "ETL", "pipeline"],
    "prompt": "Design a data pipeline architecture for [use case]. Include: data source inventory, ingestion strategy (batch vs streaming), transformation logic (cleaning, enrichment, aggregation), storage layer (data warehouse, data lake), orchestration tool selection (Airflow, Dagster, Prefect), data quality checks, monitoring and alerting, schema evolution strategy, and cost estimation. Provide a diagram description and implementation plan.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "complex",
    "estimated_credits": 70
  },
  {
    "id": "okr-planning",
    "title": "OKR Planning Template",
    "description": "Define company and team OKRs with measurable key results.",
    "category": "Productivity",
    "tags": ["OKRs", "goal setting", "planning"],
    "prompt": "Create a quarterly OKR plan for [company/team]. Define 3-5 objectives, each with 3-4 measurable key results. For each key result: current baseline, target, measurement method, and owner. Include: alignment to company mission, dependencies between team OKRs, confidence levels (0.3-0.7 range), weekly check-in template, and end-of-quarter scoring guide. Follow the Measure What Matters framework.",
    "required_connectors": [],
    "expected_artifacts": ["document", "spreadsheet"],
    "complexity": "moderate",
    "estimated_credits": 45
  },
  {
    "id": "ab-test-plan",
    "title": "A/B Test Plan",
    "description": "Design a rigorous A/B test with hypothesis, metrics, and statistical approach.",
    "category": "Research",
    "tags": ["A/B testing", "experimentation", "data science"],
    "prompt": "Design an A/B test plan for [what you want to test]. Include: hypothesis statement, primary and secondary metrics, minimum detectable effect, sample size calculation, test duration estimate, randomization approach, segmentation criteria, success criteria, guardrail metrics, analysis plan (frequentist or Bayesian), and a decision framework (ship/iterate/kill). Account for novelty effects and multiple comparisons.",
    "required_connectors": [],
    "expected_artifacts": ["document"],
    "complexity": "moderate",
    "estimated_credits": 40
  }
]
```

## 3. Create `backend/gallery/service.py`

```python
"""Prompt gallery service — loads and serves curated templates."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_templates: list[dict[str, Any]] = []
_categories: list[str] = []


def _load_templates() -> None:
    """Load templates from the JSON seed file."""
    global _templates, _categories
    templates_path = Path(__file__).parent / "templates.json"
    if not templates_path.exists():
        logger.warning("Gallery templates.json not found at %s", templates_path)
        return
    with open(templates_path) as f:
        _templates = json.load(f)
    _categories = sorted(set(t.get("category", "Other") for t in _templates))
    logger.info("Loaded %d gallery templates in %d categories", len(_templates), len(_categories))


class GalleryService:
    """Query and filter prompt templates."""

    @staticmethod
    def get_all() -> list[dict[str, Any]]:
        if not _templates:
            _load_templates()
        return _templates

    @staticmethod
    def get_categories() -> list[str]:
        if not _categories:
            _load_templates()
        return _categories

    @staticmethod
    def search(
        query: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        complexity: str | None = None,
    ) -> list[dict[str, Any]]:
        if not _templates:
            _load_templates()

        results = _templates
        if category:
            results = [t for t in results if t.get("category", "").lower() == category.lower()]
        if complexity:
            results = [t for t in results if t.get("complexity", "").lower() == complexity.lower()]
        if tags:
            tag_set = set(tag.lower() for tag in tags)
            results = [t for t in results if tag_set.intersection(set(tg.lower() for tg in t.get("tags", [])))]
        if query:
            q = query.lower()
            results = [
                t for t in results
                if q in t.get("title", "").lower()
                or q in t.get("description", "").lower()
                or any(q in tag.lower() for tag in t.get("tags", []))
            ]
        return results

    @staticmethod
    def get_by_id(template_id: str) -> dict[str, Any] | None:
        if not _templates:
            _load_templates()
        for t in _templates:
            if t["id"] == template_id:
                return t
        return None

    @staticmethod
    def get_suggestions(limit: int = 6) -> list[dict[str, Any]]:
        """Return a curated selection for suggestion chips."""
        if not _templates:
            _load_templates()
        # Pick one from each category for variety
        seen_categories: set[str] = set()
        suggestions: list[dict[str, Any]] = []
        for t in _templates:
            cat = t.get("category", "")
            if cat not in seen_categories:
                seen_categories.add(cat)
                suggestions.append({"id": t["id"], "title": t["title"], "category": cat})
                if len(suggestions) >= limit:
                    break
        return suggestions
```

## 4. Create `backend/gallery/router.py`

```python
"""API routes for the prompt gallery."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from backend.gallery.service import GalleryService

gallery_router = APIRouter(prefix="/api/gallery", tags=["gallery"])


@gallery_router.get("/")
async def list_templates(
    category: str | None = Query(None),
    query: str | None = Query(None, alias="q"),
    complexity: str | None = Query(None),
    tag: str | None = Query(None),
) -> dict[str, Any]:
    """List and filter prompt templates."""
    tags = [tag] if tag else None
    templates = GalleryService.search(query=query, category=category, tags=tags, complexity=complexity)
    return {"ok": True, "templates": templates, "total": len(templates)}


@gallery_router.get("/categories")
async def list_categories() -> dict[str, Any]:
    """List available template categories."""
    return {"ok": True, "categories": GalleryService.get_categories()}


@gallery_router.get("/suggestions")
async def get_suggestions(limit: int = Query(6, ge=1, le=12)) -> dict[str, Any]:
    """Get suggestion chips for the input bar."""
    return {"ok": True, "suggestions": GalleryService.get_suggestions(limit)}


@gallery_router.get("/{template_id}")
async def get_template(template_id: str) -> dict[str, Any]:
    """Get a single template by ID."""
    template = GalleryService.get_by_id(template_id)
    if not template:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Template not found")
    return {"ok": True, "template": template}
```

## 5. Register router in `main.py`

Add import:
```python
from backend.gallery.router import gallery_router
```

Add registration:
```python
app.include_router(gallery_router)
```

## 6. Create `frontend/src/components/PromptGallery.tsx`

A full-page gallery with category tabs, search, and clickable template cards.

```tsx
import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../lib/api'

type Template = {
  id: string
  title: string
  description: string
  category: string
  tags: string[]
  prompt: string
  required_connectors: string[]
  expected_artifacts: string[]
  complexity: 'simple' | 'moderate' | 'complex'
  estimated_credits: number
}

type PromptGalleryProps = {
  onSelectTemplate: (prompt: string) => void
  onClose: () => void
}

const COMPLEXITY_COLORS: Record<string, string> = {
  simple: 'bg-emerald-900/30 text-emerald-400',
  moderate: 'bg-blue-900/30 text-blue-400',
  complex: 'bg-amber-900/30 text-amber-400',
}

export function PromptGallery({ onSelectTemplate, onClose }: PromptGalleryProps) {
  const [templates, setTemplates] = useState<Template[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [activeCategory, setActiveCategory] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchTemplates = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (activeCategory) params.set('category', activeCategory)
      if (searchQuery) params.set('q', searchQuery)
      const resp = await fetch(apiUrl(`/api/gallery/?${params}`), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setTemplates(data.templates)
    } catch { /* silent */ } finally {
      setLoading(false)
    }
  }, [activeCategory, searchQuery])

  const fetchCategories = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/gallery/categories'), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setCategories(data.categories)
    } catch { /* silent */ }
  }, [])

  useEffect(() => {
    fetchCategories()
  }, [fetchCategories])

  useEffect(() => {
    fetchTemplates()
  }, [fetchTemplates])

  return (
    <div className="flex h-full flex-col rounded-2xl border border-[#2a2a2a] bg-[#1a1a1a]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#2a2a2a] px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Prompt Gallery</h2>
          <p className="mt-0.5 text-xs text-zinc-400">Browse curated workflows and launch with one click</p>
        </div>
        <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-300">✕</button>
      </div>

      {/* Search + category tabs */}
      <div className="border-b border-[#2a2a2a] px-6 py-3">
        <input
          type="text"
          placeholder="Search templates..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="mb-3 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
        />
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setActiveCategory(null)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              !activeCategory ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
            }`}
          >
            All
          </button>
          {categories.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setActiveCategory(cat)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                activeCategory === cat ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Template grid */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          </div>
        ) : templates.length === 0 ? (
          <p className="py-12 text-center text-sm text-zinc-500">No templates found</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {templates.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => onSelectTemplate(t.prompt)}
                className="group rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 text-left transition-all hover:border-blue-600/50 hover:bg-zinc-900"
              >
                <div className="flex items-start justify-between">
                  <h3 className="text-sm font-semibold text-white group-hover:text-blue-300">{t.title}</h3>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${COMPLEXITY_COLORS[t.complexity] || ''}`}>
                    {t.complexity}
                  </span>
                </div>
                <p className="mt-1.5 text-xs text-zinc-400 line-clamp-2">{t.description}</p>
                <div className="mt-3 flex flex-wrap gap-1">
                  <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">{t.category}</span>
                  {t.tags.slice(0, 2).map((tag) => (
                    <span key={tag} className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">{tag}</span>
                  ))}
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <span className="text-[10px] text-zinc-600">~{t.estimated_credits} credits</span>
                  {t.required_connectors.length > 0 && (
                    <span className="text-[10px] text-amber-500">Requires: {t.required_connectors.join(', ')}</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
```

## 7. Create `frontend/src/components/SuggestionChips.tsx`

A row of quick-start pills that sits above the InputBar.

```tsx
import { useCallback, useEffect, useState } from 'react'
import { apiUrl } from '../lib/api'

type Suggestion = {
  id: string
  title: string
  category: string
}

type SuggestionChipsProps = {
  onSelectSuggestion: (templateId: string) => void
  onOpenGallery: () => void
}

export function SuggestionChips({ onSelectSuggestion, onOpenGallery }: SuggestionChipsProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])

  const fetchSuggestions = useCallback(async () => {
    try {
      const resp = await fetch(apiUrl('/api/gallery/suggestions?limit=5'), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setSuggestions(data.suggestions)
    } catch { /* silent */ }
  }, [])

  useEffect(() => {
    fetchSuggestions()
  }, [fetchSuggestions])

  if (suggestions.length === 0) return null

  return (
    <div className="flex items-center gap-2 overflow-x-auto px-2 py-1.5">
      <button
        type="button"
        onClick={onOpenGallery}
        className="shrink-0 rounded-full border border-blue-600/50 bg-blue-900/20 px-3 py-1 text-xs font-medium text-blue-300 hover:bg-blue-900/40"
      >
        From the gallery
      </button>
      {suggestions.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() => onSelectSuggestion(s.id)}
          className="shrink-0 rounded-full border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-300"
        >
          {s.title}
        </button>
      ))}
    </div>
  )
}
```

---

## Verification
1. `cd frontend && npm run build` — zero errors
2. `cd frontend && npm run lint` — zero errors
3. Backend starts without errors, templates load on first request
4. `GET /api/gallery/` returns all 25 templates
5. `GET /api/gallery/?category=Engineering` filters correctly
6. `GET /api/gallery/?q=competitor` searches correctly
7. `GET /api/gallery/categories` returns sorted category list
8. `GET /api/gallery/suggestions` returns 6 varied suggestions
9. `GET /api/gallery/competitor-battlecards` returns single template
10. PromptGallery renders with category tabs, search, and clickable cards
11. SuggestionChips renders as a horizontal scrollable row
