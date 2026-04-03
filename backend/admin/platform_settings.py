"""Admin endpoint for platform-wide settings (global system instruction, etc.)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.dependencies import get_admin_user
from backend.database import PlatformSetting, User, get_session

router = APIRouter(prefix="/platform-settings", tags=["admin-platform-settings"])

GLOBAL_INSTRUCTION_KEY = "aegis_global_system_instruction"


class PatchPlatformSettingsBody(BaseModel):
    global_system_instruction: str


async def _get_value(db: AsyncSession, key: str) -> str:
    result = await db.execute(select(PlatformSetting).where(PlatformSetting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else ""


async def _set_value(db: AsyncSession, key: str, value: str, admin_uid: str) -> None:
    result = await db.execute(select(PlatformSetting).where(PlatformSetting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
        row.updated_by = admin_uid
    else:
        db.add(PlatformSetting(key=key, value=value, updated_by=admin_uid))
    await db.commit()


@router.get("")
async def get_platform_settings(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return current platform-wide settings (admin only)."""
    _ = admin
    return {
        "global_system_instruction": await _get_value(db, GLOBAL_INSTRUCTION_KEY),
    }


@router.patch("")
async def patch_platform_settings(
    body: PatchPlatformSettingsBody,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update platform-wide settings (admin only)."""
    await _set_value(db, GLOBAL_INSTRUCTION_KEY, body.global_system_instruction, admin.uid)
    return {
        "global_system_instruction": body.global_system_instruction,
    }
