"""API routes for the prompt gallery."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.gallery.service import GalleryService

gallery_router = APIRouter(prefix="/api/gallery", tags=["gallery"])


@gallery_router.get("/")
async def list_templates(
    category: str | None = Query(None),
    query: str | None = Query(None, alias="q"),
    complexity: str | None = Query(None),
    tag: str | None = Query(None),
) -> dict[str, Any]:
    """List and filter prompt templates."""
    tags = [tag] if tag else None
    templates = GalleryService.search(query=query, category=category, tags=tags, complexity=complexity)
    return {"ok": True, "templates": templates, "total": len(templates)}


@gallery_router.get("/categories")
async def list_categories() -> dict[str, Any]:
    """List available template categories."""
    return {"ok": True, "categories": GalleryService.get_categories()}


@gallery_router.get("/suggestions")
async def get_suggestions(limit: int = Query(6, ge=1, le=12)) -> dict[str, Any]:
    """Get suggestion chips for the input bar."""
    return {"ok": True, "suggestions": GalleryService.get_suggestions(limit)}


@gallery_router.get("/{template_id}")
async def get_template(template_id: str) -> dict[str, Any]:
    """Get a single template by ID."""
    template = GalleryService.get_by_id(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"ok": True, "template": template}
