"""Admin endpoint for platform-wide settings (global system instruction, etc.)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.admin.audit_service import log_admin_action
from backend.admin.dependencies import get_admin_user
from backend.database import PlatformSetting, User, get_session
from backend.modes import (
    ADMIN_EDITABLE_MODE_METADATA_FIELDS,
    MODE_LABELS,
    PROTECTED_MODE_POLICY_FIELDS,
    mode_definitions,
    normalize_agent_mode,
    serialize_mode_definition,
)

router = APIRouter(prefix="/platform-settings", tags=["admin-platform-settings"])

GLOBAL_INSTRUCTION_KEY = "aegis_global_system_instruction"
MODE_INSTRUCTION_KEY_PREFIX = "aegis_mode_system_instruction:"
MODE_METADATA_KEY_PREFIX = "aegis_mode_metadata:"


class PatchPlatformSettingsBody(BaseModel):
    global_system_instruction: str
    mode_system_instructions: dict[str, str] | None = None
    mode_metadata: dict[str, dict[str, Any]] | None = None
    mode_policy: dict[str, dict[str, Any]] | None = None

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

    @field_validator("mode_metadata")
    @classmethod
    def _validate_mode_metadata(cls, value: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]] | None:
        if value is None:
            return value
        for mode, metadata in value.items():
            normalized = normalize_agent_mode(mode)
            if mode != normalized:
                raise ValueError(f"Unsupported mode key: {mode}")
            unknown = sorted(set(metadata) - ADMIN_EDITABLE_MODE_METADATA_FIELDS)
            if unknown:
                raise ValueError(f"Unsupported metadata fields for mode '{mode}': {', '.join(unknown)}")
            for key, raw in metadata.items():
                if key == "sort_order":
                    if not isinstance(raw, int):
                        raise ValueError(f"mode_metadata.{mode}.sort_order must be an integer")
                    continue
                if not isinstance(raw, str):
                    raise ValueError(f"mode_metadata.{mode}.{key} must be a string")
        return value

    @field_validator("mode_policy")
    @classmethod
    def _reject_mode_policy_mutation(cls, value: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]] | None:
        if value:
            raise ValueError(
                "Mode policy is immutable and system-owned; create/delete/rename/policy-field edits are not allowed."
            )
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


def _mode_metadata_key(mode: str) -> str:
    return f"{MODE_METADATA_KEY_PREFIX}{normalize_agent_mode(mode)}"


async def _get_mode_instruction_map(db: AsyncSession) -> dict[str, str]:
    instructions: dict[str, str] = {}
    for mode in MODE_LABELS:
        instructions[mode] = await _get_value(db, _mode_instruction_key(mode))
    return instructions


async def _get_mode_metadata_map(db: AsyncSession) -> dict[str, dict[str, Any]]:
    metadata_map: dict[str, dict[str, Any]] = {}
    for mode in MODE_LABELS:
        raw_value = await _get_value(db, _mode_metadata_key(mode))
        if not raw_value.strip():
            metadata_map[mode] = {}
            continue
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            metadata_map[mode] = {}
            continue
        if isinstance(parsed, dict):
            filtered = {k: parsed[k] for k in ADMIN_EDITABLE_MODE_METADATA_FIELDS if k in parsed}
            metadata_map[mode] = filtered
        else:
            metadata_map[mode] = {}
    return metadata_map


@router.get("")
async def get_platform_settings(
    request: Request,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return current platform-wide settings (admin only)."""
    _ = admin
    _ = request
    return {
        "global_system_instruction": await _get_value(db, GLOBAL_INSTRUCTION_KEY),
        "mode_system_instructions": await _get_mode_instruction_map(db),
        "mode_metadata": await _get_mode_metadata_map(db),
        "mode_registry": [serialize_mode_definition(mode.key) for mode in mode_definitions()],
    }


@router.patch("")
async def patch_platform_settings(
    body: PatchPlatformSettingsBody,
    request: Request,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update platform-wide settings (admin only)."""
    if body.mode_policy:
        protected = sorted({field for payload in body.mode_policy.values() for field in payload} & PROTECTED_MODE_POLICY_FIELDS)
        if protected:
            raise HTTPException(
                status_code=400,
                detail=f"Protected mode policy fields are immutable: {', '.join(protected)}",
            )

    await _set_value(db, GLOBAL_INSTRUCTION_KEY, body.global_system_instruction, admin.uid)
    if body.mode_system_instructions is not None:
        for mode, instruction in body.mode_system_instructions.items():
            await _set_value(db, _mode_instruction_key(mode), instruction, admin.uid)
    if body.mode_metadata is not None:
        for mode, metadata in body.mode_metadata.items():
            await _set_value(db, _mode_metadata_key(mode), json.dumps(metadata), admin.uid)
    await log_admin_action(
        db,
        admin_id=admin.uid,
        action="mode_registry.admin_edit",
        details={
            "updated_modes_instruction": sorted((body.mode_system_instructions or {}).keys()),
            "updated_modes_metadata": sorted((body.mode_metadata or {}).keys()),
            "global_instruction_updated": True,
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    mode_map = await _get_mode_instruction_map(db)
    return {
        "global_system_instruction": body.global_system_instruction,
        "mode_system_instructions": mode_map,
        "mode_metadata": await _get_mode_metadata_map(db),
        "mode_registry": [serialize_mode_definition(mode.key) for mode in mode_definitions()],
    }
