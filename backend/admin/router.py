"""Admin API router — mounts all implemented admin sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from . import audit, billing, conversations, dashboard, impersonation, users

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_router.include_router(dashboard.router, prefix="/dashboard")
admin_router.include_router(users.router, prefix="/users")
admin_router.include_router(billing.router, prefix="/billing")
admin_router.include_router(conversations.router, prefix="/conversations")
admin_router.include_router(impersonation.router, prefix="/impersonate")
admin_router.include_router(audit.router, prefix="/audit")
