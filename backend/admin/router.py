"""Admin API router placeholders."""

from fastapi import APIRouter

from . import billing, dashboard

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_router.include_router(dashboard.router, prefix="/dashboard")
admin_router.include_router(billing.router, prefix="/billing")
