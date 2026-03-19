"""Admin API router — mounts all implemented admin sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from . import conversations, dashboard

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_router.include_router(dashboard.router, prefix="/dashboard")
admin_router.include_router(conversations.router)
