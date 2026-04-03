"""Artifact service — stores generated files and metadata.

Storage strategy (in priority order):
1. AWS S3 — when AWS_S3_BUCKET + AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY are set.
   Files are uploaded to s3://<bucket>/artifacts/<user_id>/<artifact_id>_<filename>.
   ``storage_path`` in the DB stores the full S3 URL (``s3://...`` scheme).
2. Local disk — fallback when S3 is not configured.
   ``storage_path`` is a relative path under ``./artifacts/``.

The router detects which mode is active by checking whether ``storage_path``
starts with ``s3://`` and issues a pre-signed redirect for S3, or a
``FileResponse`` for local paths.
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Artifact

logger = logging.getLogger(__name__)

# Thread pool for blocking boto3 calls (kept small — artifacts are infrequent)
_S3_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="s3-artifact")


def _s3_config() -> dict | None:
    """Return S3 config dict if all required env vars are set, else None."""
    import os
    bucket = os.environ.get("AWS_S3_BUCKET", "").strip()
    region = os.environ.get("AWS_S3_REGION", "us-east-1").strip()
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    if not (bucket and access_key and secret_key):
        return None
    return {"bucket": bucket, "region": region, "access_key": access_key, "secret_key": secret_key}


def _s3_client(cfg: dict):
    """Create a boto3 S3 client from the given config dict."""
    import boto3
    return boto3.client(
        "s3",
        region_name=cfg["region"],
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
    )


def _upload_to_s3_sync(cfg: dict, key: str, content: bytes, mime_type: str) -> str:
    """Synchronous S3 upload. Returns the s3:// URI."""
    client = _s3_client(cfg)
    client.put_object(
        Bucket=cfg["bucket"],
        Key=key,
        Body=content,
        ContentType=mime_type,
    )
    return f"s3://{cfg['bucket']}/{key}"


def _delete_from_s3_sync(cfg: dict, key: str) -> None:
    """Synchronous S3 delete."""
    client = _s3_client(cfg)
    try:
        client.delete_object(Bucket=cfg["bucket"], Key=key)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to delete S3 object: %s/%s", cfg["bucket"], key)


def _presign_s3_sync(cfg: dict, key: str, filename: str, expires: int = 3600) -> str:
    """Generate a pre-signed GET URL."""
    client = _s3_client(cfg)
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": cfg["bucket"],
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=expires,
    )


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
        cfg = _s3_config()

        if cfg:
            # ── S3 path ──────────────────────────────────────────────
            s3_key = f"artifacts/{user_id}/{artifact_id}_{filename}"
            try:
                storage_path = await asyncio.get_event_loop().run_in_executor(
                    _S3_EXECUTOR,
                    _upload_to_s3_sync,
                    cfg,
                    s3_key,
                    content,
                    mime_type,
                )
            except Exception:
                logger.exception("S3 upload failed for artifact %s; falling back to local storage", artifact_id)
                storage_path = None  # will fall through to local below

        if not cfg or storage_path is None:  # type: ignore[possibly-undefined]
            # ── Local disk path ───────────────────────────────────────
            root = ArtifactService._storage_root()
            user_dir = root / user_id
            user_dir.mkdir(parents=True, exist_ok=True)
            file_path = user_dir / f"{artifact_id}_{filename}"
            file_path.write_bytes(content)
            storage_path = str(file_path.relative_to(root))

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
            storage_path=storage_path,
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
        """Return the local file path for a local-storage artifact.

        Returns ``None`` for S3-backed artifacts (caller should use
        ``get_download_url`` instead).
        """
        result = await session.execute(select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id))
        artifact = result.scalar_one_or_none()
        if not artifact:
            return None
        if artifact.storage_path.startswith("s3://"):
            return None  # S3 artifact — use get_download_url
        artifact.download_count = (artifact.download_count or 0) + 1
        await session.commit()
        return ArtifactService._storage_root() / artifact.storage_path

    @staticmethod
    async def get_download_url(session: AsyncSession, artifact_id: str, user_id: str) -> str | None:
        """Return a pre-signed S3 URL for an S3-backed artifact.

        Returns ``None`` for local-storage artifacts (use ``get_file_path``).
        """
        result = await session.execute(select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id))
        artifact = result.scalar_one_or_none()
        if not artifact or not artifact.storage_path.startswith("s3://"):
            return None

        cfg = _s3_config()
        if not cfg:
            return None

        # Parse s3://bucket/key
        s3_path = artifact.storage_path[len("s3://"):]
        bucket, _, key = s3_path.partition("/")
        if bucket != cfg["bucket"]:
            # If bucket changed, use key as-is
            key = s3_path.split("/", 1)[-1]

        safe_filename = artifact.filename
        artifact.download_count = (artifact.download_count or 0) + 1
        await session.commit()

        try:
            url = await asyncio.get_event_loop().run_in_executor(
                _S3_EXECUTOR,
                _presign_s3_sync,
                cfg,
                key,
                safe_filename,
                3600,
            )
            return url
        except Exception:
            logger.exception("Failed to generate pre-signed URL for %s", artifact_id)
            return None

    @staticmethod
    async def delete_artifact(session: AsyncSession, artifact_id: str, user_id: str) -> bool:
        result = await session.execute(select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id))
        artifact = result.scalar_one_or_none()
        if not artifact:
            return False

        if artifact.storage_path.startswith("s3://"):
            # Delete from S3
            cfg = _s3_config()
            if cfg:
                s3_path = artifact.storage_path[len("s3://"):]
                key = s3_path.split("/", 1)[-1]
                await asyncio.get_event_loop().run_in_executor(
                    _S3_EXECUTOR,
                    _delete_from_s3_sync,
                    cfg,
                    key,
                )
        else:
            # Delete from local disk
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
        "storage_backend": "s3" if artifact.storage_path.startswith("s3://") else "local",
    }
