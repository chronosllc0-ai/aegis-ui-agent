"""Admin endpoint for platform-wide settings (global system instruction, etc.)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.dependencies import get_admin_user
from backend.database import PlatformSetting, User, get_session
from backend.modes import MODE_LABELS, normalize_agent_mode

router = APIRouter(prefix="/platform-settings", tags=["admin-platform-settings"])

GLOBAL_INSTRUCTION_KEY = "aegis_global_system_instruction"
MODE_INSTRUCTION_KEY_PREFIX = "aegis_mode_system_instruction:"


class PatchPlatformSettingsBody(BaseModel):
    global_system_instruction: str
    mode_system_instructions: dict[str, str] | None = None

    @field_validator("mode_system_instructions")
    @classmethod
    def _validate_mode_map(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return value
        for mode in value:
            normalized = normalize_agent_mode(mode)
            if mode != normalized:
                raise ValueError(f"Unsupported mode key: {mode}")
        return value


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


def _mode_instruction_key(mode: str) -> str:
    return f"{MODE_INSTRUCTION_KEY_PREFIX}{normalize_agent_mode(mode)}"


async def _get_mode_instruction_map(db: AsyncSession) -> dict[str, str]:
    instructions: dict[str, str] = {}
    for mode in MODE_LABELS:
        instructions[mode] = await _get_value(db, _mode_instruction_key(mode))
    return instructions


@router.get("")
async def get_platform_settings(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return current platform-wide settings (admin only)."""
    _ = admin
    return {
        "global_system_instruction": await _get_value(db, GLOBAL_INSTRUCTION_KEY),
        "mode_system_instructions": await _get_mode_instruction_map(db),
    }


@router.patch("")
async def patch_platform_settings(
    body: PatchPlatformSettingsBody,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update platform-wide settings (admin only)."""
    await _set_value(db, GLOBAL_INSTRUCTION_KEY, body.global_system_instruction, admin.uid)
    if body.mode_system_instructions is not None:
        for mode, instruction in body.mode_system_instructions.items():
            await _set_value(db, _mode_instruction_key(mode), instruction, admin.uid)
    await db.commit()
    mode_map = await _get_mode_instruction_map(db)
    return {
        "global_system_instruction": body.global_system_instruction,
        "mode_system_instructions": mode_map,
    }
