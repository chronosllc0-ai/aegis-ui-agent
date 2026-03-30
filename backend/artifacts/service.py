"""Artifact service — store and retrieve generated files."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Artifact
from config import settings

ARTIFACT_STORAGE_PATH = getattr(settings, "ARTIFACT_STORAGE_PATH", "./artifacts")

ARTIFACT_TYPES = {
    "document": {"mime": "text/markdown", "ext": ".md"},
    "html": {"mime": "text/html", "ext": ".html"},
    "code": {"mime": "text/plain", "ext": ".txt"},
    "spreadsheet": {"mime": "text/csv", "ext": ".csv"},
    "image": {"mime": "image/png", "ext": ".png"},
    "pdf": {"mime": "application/pdf", "ext": ".pdf"},
    "json": {"mime": "application/json", "ext": ".json"},
}

CODE_EXTENSIONS = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "html": ".html",
    "css": ".css",
    "sql": ".sql",
    "rust": ".rs",
    "go": ".go",
    "java": ".java",
    "bash": ".sh",
    "yaml": ".yaml",
    "toml": ".toml",
}


class ArtifactService:
    """Manages artifact lifecycle."""

    @staticmethod
    def _ensure_storage() -> Path:
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
        from datetime import datetime, timezone

        storage_dir = ArtifactService._ensure_storage()
        artifact_id = str(uuid4())
        type_info = ARTIFACT_TYPES.get(artifact_type, ARTIFACT_TYPES["document"])
        if not mime_type:
            mime_type = type_info["mime"]

        ext = type_info["ext"]
        if artifact_type == "code" and language:
            ext = CODE_EXTENSIONS.get(language, ext)

        if not filename:
            safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)[:50].strip() or "artifact"
            filename = f"{safe_title}{ext}"

        now = datetime.now(timezone.utc)
        relative_dir = f"{user_id}/{now.strftime('%Y-%m')}"
        full_dir = storage_dir / relative_dir
        full_dir.mkdir(parents=True, exist_ok=True)

        storage_filename = f"{artifact_id}_{filename}"
        storage_path = f"{relative_dir}/{storage_filename}"
        full_path = storage_dir / storage_path

        content_bytes = content.encode("utf-8") if isinstance(content, str) else content
        full_path.write_bytes(content_bytes)

        content_preview = None
        if artifact_type in {"document", "code", "html", "json", "spreadsheet"}:
            text_content = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
            content_preview = text_content[:500]

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
        artifact = (
            await session.execute(select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id))
        ).scalar_one_or_none()
        return _artifact_to_dict(artifact) if artifact else None

    @staticmethod
    async def list_artifacts(
        session: AsyncSession,
        user_id: str,
        conversation_id: str | None = None,
        artifact_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
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
        return [_artifact_to_dict(a) for a in (await session.execute(stmt)).scalars().all()]

    @staticmethod
    def get_file_path(artifact: dict) -> Path | None:
        full = Path(ARTIFACT_STORAGE_PATH) / artifact["storage_path"]
        return full if full.exists() else None

    @staticmethod
    async def record_download(session: AsyncSession, artifact_id: str) -> None:
        await session.execute(update(Artifact).where(Artifact.id == artifact_id).values(download_count=Artifact.download_count + 1))
        await session.commit()

    @staticmethod
    async def toggle_pin(session: AsyncSession, artifact_id: str, user_id: str) -> dict | None:
        artifact = (
            await session.execute(select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id))
        ).scalar_one_or_none()
        if not artifact:
            return None
        artifact.is_pinned = not bool(artifact.is_pinned)
        await session.commit()
        await session.refresh(artifact)
        return _artifact_to_dict(artifact)

    @staticmethod
    async def delete_artifact(session: AsyncSession, artifact_id: str, user_id: str) -> bool:
        artifact = (
            await session.execute(select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id))
        ).scalar_one_or_none()
        if not artifact:
            return False
        file_path = Path(ARTIFACT_STORAGE_PATH) / artifact.storage_path
        if file_path.exists():
            file_path.unlink()
        await session.execute(delete(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id))
        await session.commit()
        return True


def _artifact_to_dict(artifact: Artifact) -> dict:
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
