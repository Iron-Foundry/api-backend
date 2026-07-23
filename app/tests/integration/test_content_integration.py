"""Real-DB lifecycle for the content router: category + entry CRUD."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

_PAGE = "resource"


async def test_content_category_and_entry_crud(staff_client: AsyncClient) -> None:
    cat_resp = await staff_client.post(
        f"/content/{_PAGE}/categories", json={"label": "Getting Started"}
    )
    assert cat_resp.status_code == 201, cat_resp.text
    cat = cat_resp.json()
    cat_id = cat["id"]
    assert cat["label"] == "Getting Started"
    assert cat["slug"] == "getting-started"

    entry_resp = await staff_client.post(
        f"/content/{_PAGE}/categories/{cat_id}/entries",
        json={"title": "Welcome", "slug": "welcome", "body": "# Hello"},
    )
    assert entry_resp.status_code == 201, entry_resp.text
    entry_id = entry_resp.json()["id"]

    fetched = await staff_client.get(f"/content/{_PAGE}/entries/{entry_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Welcome"

    # Category tree lists the new category.
    cats = await staff_client.get(f"/content/{_PAGE}/categories")
    assert cats.status_code == 200
    assert any(c["id"] == cat_id for c in cats.json())

    updated = await staff_client.put(
        f"/content/{_PAGE}/entries/{entry_id}",
        json={"title": "Welcome (edited)", "body": "# Hi"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Welcome (edited)"

    deleted = await staff_client.delete(f"/content/{_PAGE}/entries/{entry_id}")
    assert deleted.status_code in (200, 204)


async def test_unknown_page_type_404(staff_client: AsyncClient) -> None:
    resp = await staff_client.post(
        "/content/not-a-page/categories", json={"label": "x"}
    )
    assert resp.status_code == 404
