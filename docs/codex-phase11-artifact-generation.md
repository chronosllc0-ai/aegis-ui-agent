# Codex Phase 11: Artifact Generation & Delivery

## Project Context
Aegis is a FastAPI + React/TypeScript app. Backend at repo root. Frontend at `frontend/`. The task planner (Phase 7) and sub-agent orchestration (Phase 8) execute complex plans. Currently, all output is plain text in chat messages. Users cannot get structured deliverables like PDFs, spreadsheets, slide decks, code files, or images as downloadable artifacts.

This phase adds an artifact system that collects, stores, and delivers structured outputs from task executions. Artifacts are displayed in a sidebar panel with preview, download, and sharing capabilities.

## What to implement
1. `backend/artifacts/` module for artifact creation, storage, and retrieval
2. Database model for artifacts with metadata
3. API endpoints for artifact CRUD and file download
4. Frontend artifact panel with inline previews and download buttons
5. Artifact types: document (markdown/HTML), code, spreadsheet (CSV), image, PDF, JSON

## CRITICAL RULES
- Do NOT modify: `orchestrator.py`, `session.py`, `navigator.py`, `analyzer.py`, `executor.py`, `mcp_client.py`
- Do NOT modify: any existing file in `backend/providers/`, `backend/connectors/`, `backend/admin/`, `backend/planner/`, `backend/gallery/`, `backend/memory/`
- Do NOT modify: `backend/credit_rates.py`, `backend/credit_service.py`, `backend/key_management.py`, `backend/conversation_service.py`
- Do NOT modify: any file in `frontend/src/components/settings/`
- Do NOT modify: `frontend/src/components/LandingPage.tsx`, `frontend/src/components/AuthPage.tsx`
- Do NOT modify: `auth.py`
- You MAY add new model classes at the bottom of `backend/database.py`
- You MAY add new imports and router registrations to `main.py`
- Artifacts are stored on local filesystem under `ARTIFACT_STORAGE_PATH` env var (default: `./artifacts/`). No cloud storage in this phase.
- ESLint strict: NO `setState` in `useEffect` bodies, NO ref access during render
- Tailwind v4 dark theme: `bg-[#111]`, `bg-[#1a1a1a]`, `border-[#2a2a2a]`, `text-zinc-*`
- Use `apiUrl('/path')` for ALL frontend API calls

---

## Database Model

Add to `backend/database.py` AFTER existing models:

```python
class Artifact(Base):
    """A generated artifact (file, document, code, etc.) from a task execution."""

    __tablename__ = "artifacts"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), ForeignKey("users.uid"), nullable=False, index=True)
    conversation_id = Column(String(255), ForeignKey("conversations.id"), nullable=True)
    plan_id = Column(String(255), nullable=True)  # FK to task_plans if Phase 7 exists
    step_id = Column(String(255), nullable=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    artifact_type = Column(String(50), nullable=False)  # document | code | spreadsheet | image | pdf | json | html
    mime_type = Column(String(200), nullable=False)
    filename = Column(String(500), nullable=False)
    file_size = Column(Integer, default=0)  # bytes
    storage_path = Column(Text, nullable=False)  # relative path under ARTIFACT_STORAGE_PATH
    content_preview = Column(Text)  # first 500 chars or base64 thumbnail
    metadata_json = Column(Text)  # JSON: language, dimensions, page_count, etc.
    is_pinned = Column(Boolean, default=False)
    download_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

---

## 1. Create `backend/artifacts/__init__.py`

```python
"""Artifact generation, storage, and delivery."""

from .service import ArtifactService

__all__ = ["ArtifactService"]
```

## 2. Create `backend/artifacts/service.py`

```python
"""Artifact service — store and retrieve generated files."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Artifact
from config import settings

logger = logging.getLogger(__name__)

ARTIFACT_STORAGE_PATH = getattr(settings, "ARTIFACT_STORAGE_PATH", "./artifacts")

# Map artifact types to MIME types and extensions
ARTIFACT_TYPES = {
    "document": {"mime": "text/markdown", "ext": ".md"},
    "html": {"mime": "text/html", "ext": ".html"},
    "code": {"mime": "text/plain", "ext": ".txt"},
    "spreadsheet": {"mime": "text/csv", "ext": ".csv"},
    "image": {"mime": "image/png", "ext": ".png"},
    "pdf": {"mime": "application/pdf", "ext": ".pdf"},
    "json": {"mime": "application/json", "ext": ".json"},
}

# Map common code languages to file extensions
CODE_EXTENSIONS = {
    "python": ".py", "javascript": ".js", "typescript": ".ts",
    "html": ".html", "css": ".css", "sql": ".sql",
    "rust": ".rs", "go": ".go", "java": ".java",
    "bash": ".sh", "yaml": ".yaml", "toml": ".toml",
}


class ArtifactService:
    """Manages artifact lifecycle."""

    @staticmethod
    def _ensure_storage() -> Path:
        """Ensure the artifact storage directory exists."""
        path = Path(ARTIFACT_STORAGE_PATH)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    async def create(
        session: AsyncSession,
        user_id: str,
        title: str,
        content: bytes | str,
        artifact_type: str = "document",
        filename: str | None = None,
        description: str | None = None,
        conversation_id: str | None = None,
        plan_id: str | None = None,
        step_id: str | None = None,
        mime_type: str | None = None,
        language: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Create and store a new artifact."""
        storage_dir = ArtifactService._ensure_storage()
        artifact_id = str(uuid4())

        # Determine file properties
        type_info = ARTIFACT_TYPES.get(artifact_type, ARTIFACT_TYPES["document"])
        if not mime_type:
            mime_type = type_info["mime"]

        ext = type_info["ext"]
        if artifact_type == "code" and language:
            ext = CODE_EXTENSIONS.get(language, ext)

        if not filename:
            safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)[:50].strip()
            filename = f"{safe_title}{ext}"

        # Build storage path: user_id/YYYY-MM/artifact_id_filename
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        relative_dir = f"{user_id}/{now.strftime('%Y-%m')}"
        full_dir = storage_dir / relative_dir
        full_dir.mkdir(parents=True, exist_ok=True)

        storage_filename = f"{artifact_id}_{filename}"
        storage_path = f"{relative_dir}/{storage_filename}"
        full_path = storage_dir / storage_path

        # Write content
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        full_path.write_bytes(content_bytes)

        # Generate preview
        content_preview = None
        if artifact_type in ("document", "code", "html", "json", "spreadsheet"):
            text_content = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
            content_preview = text_content[:500]

        # Build metadata
        meta = metadata or {}
        if language:
            meta["language"] = language

        artifact = Artifact(
            id=artifact_id,
            user_id=user_id,
            conversation_id=conversation_id,
            plan_id=plan_id,
            step_id=step_id,
            title=title,
            description=description,
            artifact_type=artifact_type,
            mime_type=mime_type,
            filename=filename,
            file_size=len(content_bytes),
            storage_path=storage_path,
            content_preview=content_preview,
            metadata_json=json.dumps(meta) if meta else None,
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)

        return _artifact_to_dict(artifact)

    @staticmethod
    async def get(session: AsyncSession, artifact_id: str, user_id: str) -> dict | None:
        """Get artifact metadata."""
        result = await session.execute(
            select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id)
        )
        a = result.scalar_one_or_none()
        return _artifact_to_dict(a) if a else None

    @staticmethod
    async def list_artifacts(
        session: AsyncSession,
        user_id: str,
        conversation_id: str | None = None,
        artifact_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List artifacts for a user."""
        stmt = (
            select(Artifact)
            .where(Artifact.user_id == user_id)
            .order_by(Artifact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if conversation_id:
            stmt = stmt.where(Artifact.conversation_id == conversation_id)
        if artifact_type:
            stmt = stmt.where(Artifact.artifact_type == artifact_type)

        result = await session.execute(stmt)
        return [_artifact_to_dict(a) for a in result.scalars().all()]

    @staticmethod
    def get_file_path(artifact: dict) -> Path | None:
        """Get the full filesystem path for an artifact."""
        storage_dir = Path(ARTIFACT_STORAGE_PATH)
        full_path = storage_dir / artifact["storage_path"]
        if full_path.exists():
            return full_path
        return None

    @staticmethod
    async def record_download(session: AsyncSession, artifact_id: str) -> None:
        """Increment the download counter."""
        await session.execute(
            update(Artifact).where(Artifact.id == artifact_id).values(
                download_count=Artifact.download_count + 1
            )
        )
        await session.commit()

    @staticmethod
    async def toggle_pin(session: AsyncSession, artifact_id: str, user_id: str) -> dict | None:
        """Toggle the pinned status of an artifact."""
        result = await session.execute(
            select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id)
        )
        a = result.scalar_one_or_none()
        if not a:
            return None
        a.is_pinned = not a.is_pinned
        await session.commit()
        await session.refresh(a)
        return _artifact_to_dict(a)

    @staticmethod
    async def delete_artifact(session: AsyncSession, artifact_id: str, user_id: str) -> bool:
        """Delete an artifact and its file."""
        result = await session.execute(
            select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id)
        )
        a = result.scalar_one_or_none()
        if not a:
            return False

        # Delete file
        storage_dir = Path(ARTIFACT_STORAGE_PATH)
        file_path = storage_dir / a.storage_path
        if file_path.exists():
            file_path.unlink()

        await session.execute(
            delete(Artifact).where(Artifact.id == artifact_id)
        )
        await session.commit()
        return True


def _artifact_to_dict(artifact: Artifact) -> dict:
    """Serialize an Artifact to a dict."""
    return {
        "id": artifact.id,
        "user_id": artifact.user_id,
        "conversation_id": artifact.conversation_id,
        "plan_id": artifact.plan_id,
        "step_id": artifact.step_id,
        "title": artifact.title,
        "description": artifact.description,
        "artifact_type": artifact.artifact_type,
        "mime_type": artifact.mime_type,
        "filename": artifact.filename,
        "file_size": artifact.file_size,
        "storage_path": artifact.storage_path,
        "content_preview": artifact.content_preview,
        "metadata": json.loads(artifact.metadata_json) if artifact.metadata_json else {},
        "is_pinned": artifact.is_pinned,
        "download_count": artifact.download_count,
        "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
    }
```

## 3. Create `backend/artifacts/router.py`

```python
"""API routes for artifact management and download."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _verify_session
from backend.database import get_session
from backend.artifacts.service import ArtifactService

logger = logging.getLogger(__name__)
artifact_router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


def _get_user_uid(request) -> str:
    token = request.cookies.get("aegis_session")
    payload = _verify_session(token)
    if not payload or "uid" not in payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return payload["uid"]


@artifact_router.get("/")
async def list_artifacts(
    request: Any,
    db: AsyncSession = Depends(get_session),
    conversation_id: str | None = Query(None),
    artifact_type: str | None = Query(None, alias="type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List user's artifacts."""
    uid = _get_user_uid(request)
    artifacts = await ArtifactService.list_artifacts(
        db, uid, conversation_id=conversation_id, artifact_type=artifact_type,
        limit=limit, offset=offset,
    )
    return {"ok": True, "artifacts": artifacts}


@artifact_router.post("/")
async def create_artifact(
    payload: dict[str, Any],
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create an artifact from text content.

    Body: {
        "title": "Report.md",
        "content": "# My Report\n...",
        "artifact_type": "document",
        "filename": "report.md",
        "description": "Monthly report",
        "conversation_id": "...",
        "language": "python"
    }
    """
    uid = _get_user_uid(request)
    title = payload.get("title", "").strip()
    content = payload.get("content", "")
    if not title or not content:
        raise HTTPException(status_code=400, detail="Title and content are required")

    artifact = await ArtifactService.create(
        db, uid,
        title=title,
        content=content,
        artifact_type=payload.get("artifact_type", "document"),
        filename=payload.get("filename"),
        description=payload.get("description"),
        conversation_id=payload.get("conversation_id"),
        plan_id=payload.get("plan_id"),
        step_id=payload.get("step_id"),
        language=payload.get("language"),
        metadata=payload.get("metadata"),
    )
    return {"ok": True, "artifact": artifact}


@artifact_router.get("/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get artifact metadata."""
    uid = _get_user_uid(request)
    artifact = await ArtifactService.get(db, artifact_id, uid)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"ok": True, "artifact": artifact}


@artifact_router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Download an artifact file."""
    uid = _get_user_uid(request)
    artifact = await ArtifactService.get(db, artifact_id, uid)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    file_path = ArtifactService.get_file_path(artifact)
    if not file_path:
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")

    await ArtifactService.record_download(db, artifact_id)

    return FileResponse(
        path=str(file_path),
        filename=artifact["filename"],
        media_type=artifact["mime_type"],
    )


@artifact_router.post("/{artifact_id}/pin")
async def toggle_pin(
    artifact_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Toggle pin status of an artifact."""
    uid = _get_user_uid(request)
    artifact = await ArtifactService.toggle_pin(db, artifact_id, uid)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"ok": True, "artifact": artifact}


@artifact_router.delete("/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    request: Any,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Delete an artifact."""
    uid = _get_user_uid(request)
    ok = await ArtifactService.delete_artifact(db, artifact_id, uid)
    if not ok:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"ok": True}
```

## 4. Register router in `main.py`

Add import:
```python
from backend.artifacts.router import artifact_router
```

Add registration:
```python
app.include_router(artifact_router)
```

Also add to `config.py` Settings class:
```python
ARTIFACT_STORAGE_PATH: str = "./artifacts"
```

## 5. Create `frontend/src/hooks/useArtifacts.ts`

```typescript
import { useCallback, useState } from 'react'
import { apiUrl } from '../lib/api'

export type ArtifactEntry = {
  id: string
  user_id: string
  conversation_id: string | null
  plan_id: string | null
  step_id: string | null
  title: string
  description: string | null
  artifact_type: string
  mime_type: string
  filename: string
  file_size: number
  storage_path: string
  content_preview: string | null
  metadata: Record<string, unknown>
  is_pinned: boolean
  download_count: number
  created_at: string | null
}

export function useArtifacts() {
  const [artifacts, setArtifacts] = useState<ArtifactEntry[]>([])
  const [loading, setLoading] = useState(false)

  const fetchArtifacts = useCallback(async (conversationId?: string, type?: string) => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (conversationId) params.set('conversation_id', conversationId)
      if (type) params.set('type', type)
      const resp = await fetch(apiUrl(`/api/artifacts/?${params}`), { credentials: 'include' })
      const data = await resp.json()
      if (data.ok) setArtifacts(data.artifacts)
    } catch { /* silent */ } finally {
      setLoading(false)
    }
  }, [])

  const downloadArtifact = useCallback(async (id: string, filename: string) => {
    try {
      const resp = await fetch(apiUrl(`/api/artifacts/${id}/download`), { credentials: 'include' })
      if (!resp.ok) return
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch { /* silent */ }
  }, [])

  const togglePin = useCallback(async (id: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/artifacts/${id}/pin`), { method: 'POST', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setArtifacts((prev) => prev.map((a) => (a.id === id ? data.artifact : a)))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  const deleteArtifact = useCallback(async (id: string): Promise<boolean> => {
    try {
      const resp = await fetch(apiUrl(`/api/artifacts/${id}`), { method: 'DELETE', credentials: 'include' })
      const data = await resp.json()
      if (data.ok) {
        setArtifacts((prev) => prev.filter((a) => a.id !== id))
        return true
      }
      return false
    } catch {
      return false
    }
  }, [])

  return { artifacts, loading, fetchArtifacts, downloadArtifact, togglePin, deleteArtifact }
}
```

## 6. Create `frontend/src/components/ArtifactPanel.tsx`

A collapsible side panel that lists artifacts for the current conversation with previews and download buttons.

```tsx
import { useCallback, useEffect, useState } from 'react'
import { useArtifacts } from '../hooks/useArtifacts'
import type { ArtifactEntry } from '../hooks/useArtifacts'

type ArtifactPanelProps = {
  conversationId?: string
  isOpen: boolean
  onToggle: () => void
}

const TYPE_ICONS: Record<string, string> = {
  document: '📄',
  code: '💻',
  spreadsheet: '📊',
  image: '🖼',
  pdf: '📕',
  json: '{ }',
  html: '🌐',
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function ArtifactPanel({ conversationId, isOpen, onToggle }: ArtifactPanelProps) {
  const { artifacts, loading, fetchArtifacts, downloadArtifact, togglePin, deleteArtifact } = useArtifacts()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen) {
      fetchArtifacts(conversationId)
    }
  }, [isOpen, conversationId, fetchArtifacts])

  const handleDownload = useCallback((a: ArtifactEntry) => {
    downloadArtifact(a.id, a.filename)
  }, [downloadArtifact])

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className="fixed right-0 top-1/2 -translate-y-1/2 rounded-l-lg border border-r-0 border-[#2a2a2a] bg-[#1a1a1a] px-2 py-4 text-xs text-zinc-400 hover:bg-zinc-800"
      >
        📎
      </button>
    )
  }

  return (
    <div className="flex h-full w-80 shrink-0 flex-col border-l border-[#2a2a2a] bg-[#1a1a1a]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#2a2a2a] px-4 py-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Artifacts</h3>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-500">{artifacts.length}</span>
          <button type="button" onClick={onToggle} className="text-zinc-500 hover:text-zinc-300">✕</button>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-3">
        {loading ? (
          <div className="flex justify-center py-8">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          </div>
        ) : artifacts.length === 0 ? (
          <p className="py-8 text-center text-xs text-zinc-600">No artifacts yet</p>
        ) : (
          <div className="space-y-2">
            {artifacts.map((a) => (
              <div key={a.id} className="group rounded-lg border border-zinc-800 bg-zinc-900/50 p-2.5">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 text-sm">{TYPE_ICONS[a.artifact_type] || '📎'}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-zinc-200">{a.title}</p>
                    <div className="mt-0.5 flex items-center gap-2">
                      <span className="text-[10px] text-zinc-600">{a.artifact_type}</span>
                      <span className="text-[10px] text-zinc-700">{formatSize(a.file_size)}</span>
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-0.5 opacity-0 group-hover:opacity-100">
                    <button type="button" onClick={() => handleDownload(a)} className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-blue-400" title="Download">
                      ↓
                    </button>
                    <button type="button" onClick={() => togglePin(a.id)} className={`rounded p-1 ${a.is_pinned ? 'text-amber-400' : 'text-zinc-600 hover:text-zinc-400'}`} title="Pin">
                      {a.is_pinned ? '★' : '☆'}
                    </button>
                    <button type="button" onClick={() => deleteArtifact(a.id)} className="rounded p-1 text-zinc-600 hover:bg-red-900/30 hover:text-red-400" title="Delete">
                      ×
                    </button>
                  </div>
                </div>

                {/* Preview toggle */}
                {a.content_preview && (
                  <button
                    type="button"
                    onClick={() => setExpandedId(expandedId === a.id ? null : a.id)}
                    className="mt-1.5 text-[10px] text-zinc-600 hover:text-zinc-400"
                  >
                    {expandedId === a.id ? 'Hide preview' : 'Show preview'}
                  </button>
                )}
                {expandedId === a.id && a.content_preview && (
                  <pre className="mt-1.5 max-h-32 overflow-auto rounded-lg bg-zinc-800/50 p-2 text-[11px] text-zinc-400">
                    {a.content_preview}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
```

---

## Verification
1. `cd frontend && npm run build` — zero errors
2. `cd frontend && npm run lint` — zero errors
3. Backend starts without import errors
4. `POST /api/artifacts/` creates an artifact and stores the file
5. `GET /api/artifacts/` lists user artifacts
6. `GET /api/artifacts/{id}` returns metadata
7. `GET /api/artifacts/{id}/download` returns the file with correct MIME type
8. `POST /api/artifacts/{id}/pin` toggles pin status
9. `DELETE /api/artifacts/{id}` removes entry and file
10. ArtifactPanel renders with preview toggle, download, pin, delete
11. File actually exists at `ARTIFACT_STORAGE_PATH/user_id/YYYY-MM/id_filename`
