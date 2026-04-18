"""Content CMS router — plugins and resources pages."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentCategory, ContentCollaborator, ContentEntry, User
from app.dependencies import get_current_user, get_session
from app.routers.surveys import _has_min_rank
from app.services.rank_mappings import get_effective_roles

router = APIRouter(prefix="/content", tags=["content"])

_VALID_PAGE_TYPES = {"plugin", "resource"}


def _slugify(label: str) -> str:
    s = label.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-") or "category"


async def _require_mentor(current_user: dict, session: AsyncSession) -> None:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    if not _has_min_rank(roles, "Mentor"):
        raise HTTPException(403, "Requires Mentor or higher.")


async def _require_senior_mod(current_user: dict, session: AsyncSession) -> None:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    if not _has_min_rank(roles, "Senior Moderator"):
        raise HTTPException(403, "Requires Senior Moderator or higher.")


def _validate_page_type(page_type: str) -> None:
    if page_type not in _VALID_PAGE_TYPES:
        raise HTTPException(404, f"Unknown page type '{page_type}'.")


# ── Public: read ──────────────────────────────────────────────────────────────

@router.get("/{page_type}/categories")
async def get_categories(
    page_type: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
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
        select(ContentEntry.id, ContentEntry.title, ContentEntry.slug, ContentEntry.category_id)
        .where(ContentEntry.category_id.in_(cat_ids))
        .order_by(ContentEntry.title)
    )
    entries_by_cat: dict = defaultdict(list)
    for entry_id, title, slug, cat_id in entries_result:
        entries_by_cat[cat_id].append({"id": str(entry_id), "title": title, "slug": slug})

    cat_map = {c.id: {
        "id": str(c.id),
        "label": c.label,
        "slug": c.slug,
        "sort_order": c.sort_order,
        "parent_id": str(c.parent_id) if c.parent_id else None,
        "children": [],
        "entries": entries_by_cat.get(c.id, []),
    } for c in all_cats}

    roots: list[dict] = []
    for c in all_cats:
        node = cat_map[c.id]
        if c.parent_id is None or c.parent_id not in cat_map:
            roots.append(node)
        else:
            cat_map[c.parent_id]["children"].append(node)

    return roots


@router.get("/{page_type}/entries/{entry_id}")
async def get_entry(
    page_type: str,
    entry_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    _validate_page_type(page_type)

    result = await session.execute(
        select(ContentEntry, User)
        .join(User, User.discord_user_id == ContentEntry.created_by, isouter=True)
        .where(ContentEntry.id == entry_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(404, "Entry not found.")
    entry, author = row

    collab_result = await session.execute(
        select(ContentCollaborator, User)
        .join(User, User.discord_user_id == ContentCollaborator.discord_user_id, isouter=True)
        .where(ContentCollaborator.entry_id == entry_id)
        .order_by(ContentCollaborator.added_at)
    )
    collaborators = [
        {
            "discord_user_id": c.discord_user_id,
            "discord_username": u.discord_username if u else None,
            "rsn": u.rsn if u else None,
            "avatar": u.discord_avatar_url if u else None,
        }
        for c, u in collab_result
    ]

    return {
        "id": str(entry.id),
        "title": entry.title,
        "body": entry.body,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        "author": {
            "discord_user_id": author.discord_user_id if author else None,
            "discord_username": author.discord_username if author else None,
            "rsn": author.rsn if author else None,
            "avatar": author.discord_avatar_url if author else None,
        } if author else None,
        "collaborators": collaborators,
    }


# ── Staff: categories ─────────────────────────────────────────────────────────

class CreateCategoryBody(BaseModel):
    label: str
    parent_id: UUID | None = None


@router.post("/{page_type}/categories", status_code=201)
async def create_category(
    page_type: str,
    body: CreateCategoryBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _validate_page_type(page_type)
    await _require_mentor(current_user, session)

    label = body.label.strip()
    if not label:
        raise HTTPException(422, "Label must not be empty.")
    slug = _slugify(label)

    if body.parent_id is not None:
        parent = (await session.execute(
            select(ContentCategory).where(
                ContentCategory.id == body.parent_id,
                ContentCategory.page_type == page_type,
            )
        )).scalar_one_or_none()
        if parent is None:
            raise HTTPException(404, "Parent category not found.")

    existing = (await session.execute(
        select(ContentCategory).where(
            ContentCategory.page_type == page_type,
            ContentCategory.parent_id == body.parent_id,
            ContentCategory.slug == slug,
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, f"Category with slug '{slug}' already exists here.")

    now = datetime.now(timezone.utc)
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


class PatchCategoryBody(BaseModel):
    label: str | None = None
    parent_id: UUID | None = None
    sort_order: int | None = None


@router.patch("/{page_type}/categories/{category_id}")
async def patch_category(
    page_type: str,
    category_id: UUID,
    body: PatchCategoryBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _validate_page_type(page_type)
    await _require_mentor(current_user, session)

    cat = (await session.execute(
        select(ContentCategory).where(
            ContentCategory.id == category_id,
            ContentCategory.page_type == page_type,
        )
    )).scalar_one_or_none()
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
            parent = (await session.execute(
                select(ContentCategory).where(
                    ContentCategory.id == new_parent_id,
                    ContentCategory.page_type == page_type,
                )
            )).scalar_one_or_none()
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
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _validate_page_type(page_type)
    await _require_senior_mod(current_user, session)

    cat = (await session.execute(
        select(ContentCategory).where(
            ContentCategory.id == category_id,
            ContentCategory.page_type == page_type,
        )
    )).scalar_one_or_none()
    if cat is None:
        raise HTTPException(404, "Category not found.")

    await session.delete(cat)
    await session.commit()
    return {"ok": True}


# ── Staff: entries ────────────────────────────────────────────────────────────

class CreateEntryBody(BaseModel):
    title: str
    body: str = ""


@router.post("/{page_type}/categories/{category_id}/entries", status_code=201)
async def create_entry(
    page_type: str,
    category_id: UUID,
    body: CreateEntryBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _validate_page_type(page_type)
    await _require_mentor(current_user, session)

    cat = (await session.execute(
        select(ContentCategory).where(
            ContentCategory.id == category_id,
            ContentCategory.page_type == page_type,
        )
    )).scalar_one_or_none()
    if cat is None:
        raise HTTPException(404, "Category not found.")

    title = body.title.strip()
    if not title:
        raise HTTPException(422, "Title must not be empty.")
    slug = _slugify(title)

    existing = (await session.execute(
        select(ContentEntry).where(
            ContentEntry.category_id == category_id,
            ContentEntry.slug == slug,
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, f"Entry with slug '{slug}' already exists in this category.")

    now = datetime.now(timezone.utc)
    entry = ContentEntry(
        category_id=category_id,
        slug=slug,
        title=title,
        body=body.body,
        created_by=int(current_user["sub"]),
        created_at=now,
        updated_at=now,
    )
    session.add(entry)
    await session.commit()

    return {
        "id": str(entry.id),
        "title": entry.title,
        "slug": entry.slug,
        "category_id": str(entry.category_id),
    }


class UpdateEntryBody(BaseModel):
    title: str | None = None
    body: str | None = None


@router.put("/{page_type}/entries/{entry_id}")
async def update_entry(
    page_type: str,
    entry_id: UUID,
    body: UpdateEntryBody,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _validate_page_type(page_type)
    await _require_mentor(current_user, session)

    entry = (await session.execute(
        select(ContentEntry).where(ContentEntry.id == entry_id)
    )).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Entry not found.")

    fields = body.model_fields_set

    if "title" in fields and body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(422, "Title must not be empty.")
        entry.title = title
        entry.slug = _slugify(title)

    if "body" in fields and body.body is not None:
        entry.body = body.body

    entry.updated_at = datetime.now(timezone.utc)

    discord_user_id = int(current_user["sub"])
    if entry.created_by != discord_user_id:
        collab_stmt = (
            pg_insert(ContentCollaborator)
            .values(
                entry_id=entry.id,
                discord_user_id=discord_user_id,
                added_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing()
        )
        await session.execute(collab_stmt)

    await session.commit()

    return {
        "id": str(entry.id),
        "title": entry.title,
        "slug": entry.slug,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


@router.delete("/{page_type}/entries/{entry_id}")
async def delete_entry(
    page_type: str,
    entry_id: UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _validate_page_type(page_type)
    await _require_senior_mod(current_user, session)

    entry = (await session.execute(
        select(ContentEntry).where(ContentEntry.id == entry_id)
    )).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Entry not found.")

    await session.delete(entry)
    await session.commit()
    return {"ok": True}
