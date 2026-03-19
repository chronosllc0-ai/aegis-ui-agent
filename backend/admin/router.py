"""Admin API router — mounts all implemented admin sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from . import users

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_router.include_router(users.router, prefix="/users")
