"""Admin API router — mounts all implemented admin sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from . import agents, audit, billing, conversations, dashboard, email, impersonation, messaging, payment_settings, platform_settings, runtime, users, workspace_files

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_router.include_router(dashboard.router, prefix="/dashboard")
admin_router.include_router(users.router, prefix="/users")
admin_router.include_router(billing.router, prefix="/billing")
admin_router.include_router(conversations.router)
admin_router.include_router(impersonation.router, prefix="/impersonate")
admin_router.include_router(audit.router, prefix="/audit")
admin_router.include_router(agents.router)
admin_router.include_router(messaging.router, prefix="/messaging")
admin_router.include_router(email.router, prefix="/email")
admin_router.include_router(payment_settings.router)
admin_router.include_router(platform_settings.router)
admin_router.include_router(runtime.router)
admin_router.include_router(workspace_files.router)
