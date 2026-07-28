from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentCategory, ContentEntry
from app.dependencies import get_current_user, get_session

from ._helpers import (
    _require_mentor,
    _require_senior_mod,
    _slugify,
    _validate_page_type,
)

router = APIRouter()


class CreateCategoryBody(BaseModel):
    label: str
    parent_id: UUID | None = None

    @field_validator("label")
    @classmethod
    def label_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("label must not be empty")
        return v


class PatchCategoryBody(BaseModel):
    label: str | None = None
    parent_id: UUID | None = None
    sort_order: int | None = None


@router.get("/{page_type}/categories")
async def get_categories(
    page_type: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Return the category tree for a page type, with its published entries."""
    _validate_page_type(page_type)

    cats_result = await session.execute(
        select(ContentCategory)
        .where(ContentCategory.page_type == page_type)
        .order_by(ContentCategory.sort_order, ContentCategory.label)
    )
    all_cats = cats_result.scalars().all()
    if not all_cats:
        return []

    cat_ids = [c.id for c in all_cats]
    entries_result = await session.execute(
        select(
            ContentEntry.id,
            ContentEntry.title,
            ContentEntry.slug,
            ContentEntry.category_id,
            ContentEntry.sort_order,
            ContentEntry.updated_at,
        )
        .where(ContentEntry.category_id.in_(cat_ids), ContentEntry.deprecated == False)  # noqa: E712
        .order_by(ContentEntry.sort_order, ContentEntry.title)
    )
    entries_by_cat: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for entry_id, title, slug, cat_id, sort_order, updated_at in entries_result:
        entries_by_cat[cat_id].append(
            {
                "id": str(entry_id),
                "title": title,
                "slug": slug,
                "sort_order": sort_order,
                "updated_at": updated_at,
            }
        )

    cat_map = {
        c.id: {
            "id": str(c.id),
            "label": c.label,
            "slug": c.slug,
            "sort_order": c.sort_order,
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "children": [],
            "entries": entries_by_cat.get(c.id, []),
        }
        for c in all_cats
    }

    roots: list[dict[str, Any]] = []
    for c in all_cats:
        node = cat_map[c.id]
        if c.parent_id is None or c.parent_id not in cat_map:
            roots.append(node)
        else:
            cat_map[c.parent_id]["children"].append(node)
    return roots


@router.post("/{page_type}/categories", status_code=201)
async def create_category(
    page_type: str,
    body: CreateCategoryBody,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a category in a page type's tree. Staff only."""
    _validate_page_type(page_type)
    await _require_mentor(current_user, session)

    label = body.label.strip()
    slug = _slugify(label)

    if body.parent_id is not None:
        parent = (
            await session.execute(
                select(ContentCategory).where(
                    ContentCategory.id == body.parent_id,
                    ContentCategory.page_type == page_type,
                )
            )
        ).scalar_one_or_none()
        if parent is None:
            raise HTTPException(404, "Parent category not found.")

    existing = (
        await session.execute(
            select(ContentCategory).where(
                ContentCategory.page_type == page_type,
                ContentCategory.parent_id == body.parent_id,
                ContentCategory.slug == slug,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, f"Category with slug '{slug}' already exists here.")

    now = datetime.now(UTC)
    cat = ContentCategory(
        page_type=page_type,
        parent_id=body.parent_id,
        slug=slug,
        label=label,
        sort_order=0,
        created_at=now,
        created_by=int(current_user["sub"]),
    )
    session.add(cat)
    await session.commit()
    return {
        "id": str(cat.id),
        "label": cat.label,
        "slug": cat.slug,
        "sort_order": cat.sort_order,
        "parent_id": str(cat.parent_id) if cat.parent_id else None,
        "children": [],
        "entries": [],
    }


@router.patch("/{page_type}/categories/{category_id}")
async def patch_category(
    page_type: str,
    category_id: UUID,
    body: PatchCategoryBody,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Rename, reorder, or re-parent a category. Staff only."""
    _validate_page_type(page_type)
    await _require_mentor(current_user, session)

    cat = (
        await session.execute(
            select(ContentCategory).where(
                ContentCategory.id == category_id,
                ContentCategory.page_type == page_type,
            )
        )
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(404, "Category not found.")

    fields = body.model_fields_set
    if "label" in fields and body.label is not None:
        label = body.label.strip()
        if not label:
            raise HTTPException(422, "Label must not be empty.")
        cat.label = label
        cat.slug = _slugify(label)

    if "parent_id" in fields:
        new_parent_id = body.parent_id
        if new_parent_id is not None and new_parent_id != cat.parent_id:
            parent = (
                await session.execute(
                    select(ContentCategory).where(
                        ContentCategory.id == new_parent_id,
                        ContentCategory.page_type == page_type,
                    )
                )
            ).scalar_one_or_none()
            if parent is None:
                raise HTTPException(404, "Parent category not found.")
        cat.parent_id = new_parent_id

    if "sort_order" in fields and body.sort_order is not None:
        cat.sort_order = body.sort_order

    await session.commit()
    return {
        "id": str(cat.id),
        "label": cat.label,
        "slug": cat.slug,
        "sort_order": cat.sort_order,
        "parent_id": str(cat.parent_id) if cat.parent_id else None,
    }


@router.delete("/{page_type}/categories/{category_id}")
async def delete_category(
    page_type: str,
    category_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Delete a category. Staff only."""
    _validate_page_type(page_type)
    await _require_senior_mod(current_user, session)

    cat = (
        await session.execute(
            select(ContentCategory).where(
                ContentCategory.id == category_id,
                ContentCategory.page_type == page_type,
            )
        )
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(404, "Category not found.")

    await session.delete(cat)
    await session.commit()
    return {"ok": True}
