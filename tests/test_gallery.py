"""Tests for prompt gallery service and API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

import main
from backend.gallery.service import GalleryService


def test_gallery_service_seed_loaded() -> None:
    """Seed file should load and expose expected minimum template counts."""
    templates = GalleryService.get_all()
    assert len(templates) >= 25
    assert GalleryService.get_by_id("competitor-battlecards") is not None


def test_gallery_routes_list_filter_search_and_detail() -> None:
    """Gallery API should support list/filter/search and template detail retrieval."""
    client = TestClient(main.app)

    all_resp = client.get("/api/gallery/")
    assert all_resp.status_code == 200
    all_data = all_resp.json()
    assert all_data["ok"] is True
    assert all_data["total"] >= 25

    filtered_resp = client.get("/api/gallery/?category=Engineering")
    assert filtered_resp.status_code == 200
    filtered_data = filtered_resp.json()
    assert filtered_data["ok"] is True
    assert all(item["category"] == "Engineering" for item in filtered_data["templates"])

    search_resp = client.get("/api/gallery/?q=competitor")
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["ok"] is True
    assert any(item["id"] == "competitor-battlecards" for item in search_data["templates"])

    categories_resp = client.get("/api/gallery/categories")
    assert categories_resp.status_code == 200
    categories_data = categories_resp.json()
    assert categories_data["ok"] is True
    assert categories_data["categories"] == sorted(categories_data["categories"])

    suggestions_resp = client.get("/api/gallery/suggestions")
    assert suggestions_resp.status_code == 200
    suggestions_data = suggestions_resp.json()
    assert suggestions_data["ok"] is True
    assert len(suggestions_data["suggestions"]) <= 6

    detail_resp = client.get("/api/gallery/competitor-battlecards")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["ok"] is True
    assert detail_data["template"]["id"] == "competitor-battlecards"


def test_gallery_route_missing_template_returns_404() -> None:
    """Unknown template IDs should return a 404 response."""
    client = TestClient(main.app)
    response = client.get("/api/gallery/not-a-real-template")
    assert response.status_code == 404


def test_github_webhook_unknown_integration_id_returns_404() -> None:
    """Webhook route should reject unknown integration IDs early."""
    client = TestClient(main.app)
    response = client.post(
        "/api/integrations/github/does-not-exist/webhook",
        json={"action": "opened"},
        headers={"X-GitHub-Event": "pull_request"},
    )
    assert response.status_code == 404
