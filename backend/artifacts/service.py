"""Artifact service — stores generated files and metadata."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Artifact


class ArtifactService:
    """CRUD and file operations for generated artifacts."""

    @staticmethod
    def _storage_root() -> Path:
        return Path("./artifacts").resolve()

    @staticmethod
    async def create_artifact(
        session: AsyncSession,
        user_id: str,
        title: str,
        artifact_type: str,
        mime_type: str,
        filename: str,
        content: bytes,
        description: str | None = None,
        conversation_id: str | None = None,
        plan_id: str | None = None,
        step_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        artifact_id = str(uuid4())
        root = ArtifactService._storage_root()
        user_dir = root / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        file_path = user_dir / f"{artifact_id}_{filename}"
        file_path.write_bytes(content)

        preview = content[:500].decode("utf-8", errors="ignore") if mime_type.startswith("text/") else None

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
            file_size=len(content),
            storage_path=str(file_path.relative_to(root)),
            content_preview=preview,
            metadata_json=json.dumps(metadata or {}),
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        return _artifact_to_dict(artifact)

    @staticmethod
    async def list_artifacts(
        session: AsyncSession,
        user_id: str,
        conversation_id: str | None = None,
        artifact_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        stmt = select(Artifact).where(Artifact.user_id == user_id)
        if conversation_id:
            stmt = stmt.where(Artifact.conversation_id == conversation_id)
        if artifact_type:
            stmt = stmt.where(Artifact.artifact_type == artifact_type)
        stmt = stmt.order_by(Artifact.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return [_artifact_to_dict(a) for a in result.scalars().all()]

    @staticmethod
    async def get_artifact(session: AsyncSession, artifact_id: str, user_id: str) -> dict | None:
        result = await session.execute(select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id))
        artifact = result.scalar_one_or_none()
        return _artifact_to_dict(artifact) if artifact else None

    @staticmethod
    async def get_file_path(session: AsyncSession, artifact_id: str, user_id: str) -> Path | None:
        result = await session.execute(select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id))
        artifact = result.scalar_one_or_none()
        if not artifact:
            return None
        artifact.download_count = (artifact.download_count or 0) + 1
        await session.commit()
        return ArtifactService._storage_root() / artifact.storage_path

    @staticmethod
    async def delete_artifact(session: AsyncSession, artifact_id: str, user_id: str) -> bool:
        result = await session.execute(select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id))
        artifact = result.scalar_one_or_none()
        if not artifact:
            return False
        file_path = ArtifactService._storage_root() / artifact.storage_path
        if file_path.exists():
            file_path.unlink()
        await session.delete(artifact)
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
