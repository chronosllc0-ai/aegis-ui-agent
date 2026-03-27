"""Prompt gallery service — loads and serves curated templates."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_templates: list[dict[str, Any]] = []
_categories: list[str] = []


def _load_templates() -> None:
    """Load templates from the JSON seed file."""
    global _templates, _categories
    templates_path = Path(__file__).parent / "templates.json"
    if not templates_path.exists():
        logger.warning("Gallery templates.json not found at %s", templates_path)
        return
    with templates_path.open(encoding="utf-8") as f:
        _templates = json.load(f)
    _categories = sorted(set(t.get("category", "Other") for t in _templates))
    logger.info("Loaded %d gallery templates in %d categories", len(_templates), len(_categories))


class GalleryService:
    """Query and filter prompt templates."""

    @staticmethod
    def get_all() -> list[dict[str, Any]]:
        """Return all templates."""
        if not _templates:
            _load_templates()
        return _templates

    @staticmethod
    def get_categories() -> list[str]:
        """Return all categories sorted alphabetically."""
        if not _categories:
            _load_templates()
        return _categories

    @staticmethod
    def search(
        query: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        complexity: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search templates by query, category, tags, and complexity."""
        if not _templates:
            _load_templates()

        results = _templates
        if category:
            results = [t for t in results if t.get("category", "").lower() == category.lower()]
        if complexity:
            results = [t for t in results if t.get("complexity", "").lower() == complexity.lower()]
        if tags:
            tag_set = {tag.lower() for tag in tags}
            results = [t for t in results if tag_set.intersection({tg.lower() for tg in t.get("tags", [])})]
        if query:
            q = query.lower()
            results = [
                t
                for t in results
                if q in t.get("title", "").lower()
                or q in t.get("description", "").lower()
                or any(q in tag.lower() for tag in t.get("tags", []))
            ]
        return results

    @staticmethod
    def get_by_id(template_id: str) -> dict[str, Any] | None:
        """Return one template by id."""
        if not _templates:
            _load_templates()
        for template in _templates:
            if template["id"] == template_id:
                return template
        return None

    @staticmethod
    def get_suggestions(limit: int = 6) -> list[dict[str, Any]]:
        """Return a curated selection for suggestion chips."""
        if not _templates:
            _load_templates()
        seen_categories: set[str] = set()
        suggestions: list[dict[str, Any]] = []
        for template in _templates:
            category = template.get("category", "")
            if category not in seen_categories:
                seen_categories.add(category)
                suggestions.append({"id": template["id"], "title": template["title"], "category": category})
                if len(suggestions) >= limit:
                    break
        return suggestions
