"""Admin endpoints for live runtime session visibility."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from backend.admin.dependencies import get_admin_user
from backend.database import User

router = APIRouter(prefix="/runtime", tags=["admin-runtime"])

_RuntimeInspector = Callable[[], dict[str, Any]]
_runtime_inspector: _RuntimeInspector | None = None


def set_runtime_inspector(inspector: _RuntimeInspector | None) -> None:
    """Register a runtime snapshot provider for admin diagnostics."""

    global _runtime_inspector
    _runtime_inspector = inspector


@router.get("/sessions")
async def list_runtime_sessions(admin: User = Depends(get_admin_user)) -> dict[str, Any]:
    """Return live session routes, queue depths, and routing health."""

    _ = admin
    if _runtime_inspector is None:
        return {"sessions": [], "summary": {"active_sessions": 0, "queued_instructions": 0}}
    snapshot = _runtime_inspector()
    return snapshot
