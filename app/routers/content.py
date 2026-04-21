"""Content CMS router — plugins and resources pages."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentCategory, ContentCollaborator, ContentEntry, ContentEntryReaction, ContentEntryVersion, User
from app.dependencies import get_current_user, get_optional_user, get_session
from app.services.page_permissions import check_page_permission
from app.services.rank_mappings import get_effective_roles

router = APIRouter(prefix="/content", tags=["content"])

_VALID_PAGE_TYPES = {"plugin", "resource"}


def _slugify(label: str) -> str:
    s = label.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-") or "category"


async def _require_mentor(current_user: dict, session: AsyncSession, page_type: str = "resource") -> None:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    page_id = "resources" if page_type == "resource" else "plugins"
    if not await check_page_permission(page_id, "create", roles, session):
        raise HTTPException(403, "Requires Foundry Mentors or higher.")


async def _slug_exists_in_page_type(
    slug: str, page_type: str, session: AsyncSession, exclude_entry_id: UUID | None = None
) -> bool:
    """Return True if any entry with this slug exists under page_type (excluding a specific entry)."""
    stmt = (
        select(ContentEntry.id)
        .join(ContentCategory, ContentEntry.category_id == ContentCategory.id)
        .where(ContentCategory.page_type == page_type, ContentEntry.slug == slug)
    )
    if exclude_entry_id is not None:
        stmt = stmt.where(ContentEntry.id != exclude_entry_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _require_senior_mod(current_user: dict, session: AsyncSession, page_type: str = "resource") -> None:
    uid = int(current_user["sub"])
    roles = await get_effective_roles(uid, session)
    page_id = "resources" if page_type == "resource" else "plugins"
    if not await check_page_permission(page_id, "delete", roles, session):
        raise HTTPException(403, "Requires Senior Moderator or higher.")


def _validate_page_type(page_type: str) -> None:
    if page_type not in _VALID_PAGE_TYPES:
        raise HTTPException(404, f"Unknown page type '{page_type}'.")



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
        select(ContentEntry.id, ContentEntry.title, ContentEntry.slug, ContentEntry.category_id, ContentEntry.sort_order)
        .where(ContentEntry.category_id.in_(cat_ids), ContentEntry.deprecated == False)  # noqa: E712
        .order_by(ContentEntry.sort_order, ContentEntry.title)
    )
    entries_by_cat: dict = defaultdict(list)
    for entry_id, title, slug, cat_id, sort_order in entries_result:
        entries_by_cat[cat_id].append({"id": str(entry_id), "title": title, "slug": slug, "sort_order": sort_order})

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


@router.get("/{page_type}/entries/by-slug/{slug}")
async def get_entry_by_slug(
    page_type: str,
    slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: dict | None = Depends(get_optional_user),
) -> dict:
    _validate_page_type(page_type)

    result = await session.execute(
        select(ContentEntry, User)
        .join(ContentCategory, ContentEntry.category_id == ContentCategory.id)
        .join(User, User.discord_user_id == ContentEntry.created_by, isouter=True)
        .where(
            ContentCategory.page_type == page_type,
            ContentEntry.slug == slug,
            ContentEntry.deprecated == False,  # noqa: E712
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(404, "Entry not found.")
    entry, author = row

    collab_result = await session.execute(
        select(ContentCollaborator, User)
        .join(User, User.discord_user_id == ContentCollaborator.discord_user_id, isouter=True)
        .where(ContentCollaborator.entry_id == entry.id)
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

    latest_version_result = await session.execute(
        select(ContentEntryVersion, User)
        .join(User, User.discord_user_id == ContentEntryVersion.edited_by, isouter=True)
        .where(ContentEntryVersion.entry_id == entry.id)
        .order_by(ContentEntryVersion.version_number.desc())
        .limit(1)
    )
    latest_version_row = latest_version_result.one_or_none()
    last_updated_by = None
    if latest_version_row:
        _, editor = latest_version_row
        if editor:
            last_updated_by = {
                "discord_user_id": editor.discord_user_id,
                "discord_username": editor.discord_username,
                "rsn": editor.rsn,
                "avatar": editor.discord_avatar_url,
            }

    # Reaction count + user_has_reacted
    reaction_count_result = await session.execute(
        select(func.count()).select_from(ContentEntryReaction).where(ContentEntryReaction.entry_id == entry.id)
    )
    reaction_count = reaction_count_result.scalar_one()
    user_has_reacted = False
    if current_user:
        uid = int(current_user["sub"])
        user_react_result = await session.execute(
            select(ContentEntryReaction).where(
                ContentEntryReaction.entry_id == entry.id,
                ContentEntryReaction.discord_user_id == uid,
            )
        )
        user_has_reacted = user_react_result.scalar_one_or_none() is not None

    return {
        "id": str(entry.id),
        "title": entry.title,
        "slug": entry.slug,
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
        "last_updated_by": last_updated_by,
        "reaction_count": reaction_count,
        "user_has_reacted": user_has_reacted,
    }


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
        .where(ContentEntry.id == entry_id, ContentEntry.deprecated == False)  # noqa: E712
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



class CreateEntryBody(BaseModel):
    title: str
    slug: str | None = None
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

    if body.slug and body.slug.strip():
        slug = _slugify(body.slug)
        if not slug:
            raise HTTPException(422, "Slug contains no valid characters.")
    else:
        slug = _slugify(title)

    if await _slug_exists_in_page_type(slug, page_type, session):
        raise HTTPException(409, f"An entry with slug '{slug}' already exists under {page_type}.")

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
    slug: str | None = None
    body: str | None = None
    sort_order: int | None = None
    expected_updated_at: datetime | None = None


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

    content_fields_check = fields - {"sort_order", "expected_updated_at"}
    if content_fields_check and body.expected_updated_at is not None and entry.updated_at is not None:
        def _to_utc(dt: datetime) -> datetime:
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        if _to_utc(body.expected_updated_at).replace(microsecond=0) != _to_utc(entry.updated_at).replace(microsecond=0):
            raise HTTPException(409, "edit_conflict")

    if "title" in fields and body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(422, "Title must not be empty.")
        entry.title = title
        if "slug" not in fields:
            entry.slug = _slugify(title)

    if "slug" in fields and body.slug is not None:
        new_slug = _slugify(body.slug.strip())
        if not new_slug:
            raise HTTPException(422, "Slug contains no valid characters.")
        if new_slug != entry.slug:
            if await _slug_exists_in_page_type(new_slug, page_type, session, exclude_entry_id=entry_id):
                raise HTTPException(409, f"An entry with slug '{new_slug}' already exists under {page_type}.")
            entry.slug = new_slug

    if "body" in fields and body.body is not None:
        entry.body = body.body

    if "sort_order" in fields and body.sort_order is not None:
        entry.sort_order = body.sort_order

    content_fields = fields - {"sort_order", "expected_updated_at"}
    if content_fields:
        uid = int(current_user["sub"])
        now = datetime.now(timezone.utc)
        entry.updated_at = now

        max_ver_result = await session.execute(
            select(func.max(ContentEntryVersion.version_number))
            .where(ContentEntryVersion.entry_id == entry_id)
        )
        max_ver = max_ver_result.scalar_one_or_none()
        next_ver = (max_ver or 0) + 1

        version = ContentEntryVersion(
            entry_id=entry.id,
            version_number=next_ver,
            title=entry.title,
            body=entry.body,
            edited_by=uid,
            created_at=now,
        )
        session.add(version)

        if entry.created_by != uid:
            collab_stmt = (
                pg_insert(ContentCollaborator)
                .values(
                    entry_id=entry.id,
                    discord_user_id=uid,
                    added_at=now,
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
    """Soft-delete: marks entry as deprecated."""
    _validate_page_type(page_type)
    await _require_mentor(current_user, session)

    entry = (await session.execute(
        select(ContentEntry).where(ContentEntry.id == entry_id)
    )).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Entry not found.")

    uid = int(current_user["sub"])
    now = datetime.now(timezone.utc)
    entry.deprecated = True
    entry.deprecated_at = now
    entry.deprecated_by = uid
    await session.commit()
    return {"ok": True}



@router.get("/{page_type}/entries/{entry_id}/versions")
async def list_entry_versions(
    page_type: str,
    entry_id: UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    _validate_page_type(page_type)
    await _require_mentor(current_user, session)

    result = await session.execute(
        select(ContentEntryVersion, User)
        .join(User, User.discord_user_id == ContentEntryVersion.edited_by, isouter=True)
        .where(ContentEntryVersion.entry_id == entry_id)
        .order_by(ContentEntryVersion.version_number.desc())
    )
    rows = result.all()

    return [
        {
            "id": v.id,
            "version_number": v.version_number,
            "title": v.title,
            "created_at": v.created_at.isoformat(),
            "edited_by": {
                "discord_user_id": u.discord_user_id,
                "discord_username": u.discord_username,
                "rsn": u.rsn,
                "avatar": u.discord_avatar_url,
            } if u else None,
        }
        for v, u in rows
    ]


@router.get("/{page_type}/entries/{entry_id}/versions/{version_id}")
async def get_entry_version(
    page_type: str,
    entry_id: UUID,
    version_id: int,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _validate_page_type(page_type)
    await _require_mentor(current_user, session)

    result = await session.execute(
        select(ContentEntryVersion, User)
        .join(User, User.discord_user_id == ContentEntryVersion.edited_by, isouter=True)
        .where(ContentEntryVersion.id == version_id, ContentEntryVersion.entry_id == entry_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(404, "Version not found.")
    v, u = row

    return {
        "id": v.id,
        "version_number": v.version_number,
        "title": v.title,
        "body": v.body,
        "created_at": v.created_at.isoformat(),
        "edited_by": {
            "discord_user_id": u.discord_user_id,
            "discord_username": u.discord_username,
            "rsn": u.rsn,
            "avatar": u.discord_avatar_url,
        } if u else None,
    }


@router.post("/{page_type}/entries/{entry_id}/revert/{version_id}")
async def revert_entry_to_version(
    page_type: str,
    entry_id: UUID,
    version_id: int,
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

    ver = (await session.execute(
        select(ContentEntryVersion).where(
            ContentEntryVersion.id == version_id,
            ContentEntryVersion.entry_id == entry_id,
        )
    )).scalar_one_or_none()
    if ver is None:
        raise HTTPException(404, "Version not found.")

    uid = int(current_user["sub"])
    now = datetime.now(timezone.utc)

    entry.title = ver.title
    entry.body = ver.body
    entry.updated_at = now

    max_ver_result = await session.execute(
        select(func.max(ContentEntryVersion.version_number))
        .where(ContentEntryVersion.entry_id == entry_id)
    )
    max_ver = max_ver_result.scalar_one_or_none()
    next_ver = (max_ver or 0) + 1

    new_version = ContentEntryVersion(
        entry_id=entry.id,
        version_number=next_ver,
        title=entry.title,
        body=entry.body,
        edited_by=uid,
        created_at=now,
    )
    session.add(new_version)

    if entry.created_by != uid:
        collab_stmt = (
            pg_insert(ContentCollaborator)
            .values(
                entry_id=entry.id,
                discord_user_id=uid,
                added_at=now,
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



@router.get("/deprecated-entries")
async def get_deprecated_entries(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    await _require_senior_mod(current_user, session)

    result = await session.execute(
        select(ContentEntry, ContentCategory, User)
        .join(ContentCategory, ContentEntry.category_id == ContentCategory.id)
        .join(User, User.discord_user_id == ContentEntry.deprecated_by, isouter=True)
        .where(ContentEntry.deprecated == True)  # noqa: E712
        .order_by(ContentEntry.deprecated_at.desc())
    )
    rows = result.all()

    return [
        {
            "id": str(e.id),
            "title": e.title,
            "slug": e.slug,
            "page_type": cat.page_type,
            "deprecated_at": e.deprecated_at.isoformat() if e.deprecated_at else None,
            "deprecated_by": {
                "discord_user_id": u.discord_user_id,
                "discord_username": u.discord_username,
                "rsn": u.rsn,
                "avatar": u.discord_avatar_url,
            } if u else None,
        }
        for e, cat, u in rows
    ]


@router.post("/{page_type}/entries/{entry_id}/restore")
async def restore_entry(
    page_type: str,
    entry_id: UUID,
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

    entry.deprecated = False
    entry.deprecated_at = None
    entry.deprecated_by = None
    await session.commit()
    return {"ok": True}


@router.delete("/{page_type}/entries/{entry_id}/permanent")
async def permanent_delete_entry(
    page_type: str,
    entry_id: UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _validate_page_type(page_type)
    await _require_senior_mod(current_user, session, page_type)

    entry = (await session.execute(
        select(ContentEntry).where(ContentEntry.id == entry_id)
    )).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Entry not found.")

    await session.delete(entry)
    await session.commit()
    return {"ok": True}


@router.post("/{page_type}/entries/{entry_id}/react")
async def toggle_reaction(
    page_type: str,
    entry_id: UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Toggle a heart reaction on a content entry. Returns updated reacted state and count."""
    _validate_page_type(page_type)
    uid = int(current_user["sub"])
    now = datetime.now(timezone.utc)

    existing = (await session.execute(
        select(ContentEntryReaction).where(
            ContentEntryReaction.entry_id == entry_id,
            ContentEntryReaction.discord_user_id == uid,
        )
    )).scalar_one_or_none()

    if existing:
        await session.delete(existing)
        reacted = False
    else:
        session.add(ContentEntryReaction(entry_id=entry_id, discord_user_id=uid, created_at=now))
        reacted = True

    await session.commit()

    count_result = await session.execute(
        select(func.count()).select_from(ContentEntryReaction).where(ContentEntryReaction.entry_id == entry_id)
    )
    count = count_result.scalar_one()
    return {"reacted": reacted, "count": count}
