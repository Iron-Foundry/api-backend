from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentCategory, ContentCollaborator, ContentEntry, ContentEntryReaction, ContentEntryVersion, User
from app.dependencies import get_current_user, get_optional_user, get_session

from ._helpers import _require_mentor, _slug_exists_in_page_type, _slugify, _validate_page_type

router = APIRouter()


class CreateEntryBody(BaseModel):
    title: str
    slug: str | None = None
    body: str = ""


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

    reaction_count_result = await session.execute(
        select(func.count()).select_from(ContentEntryReaction)
        .where(ContentEntryReaction.entry_id == entry.id)
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
        "updated_at": entry.updated_at.isoformat() if entry.updated_at is not None else None,
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
        "updated_at": entry.updated_at.isoformat() if entry.updated_at is not None else None,
        "author": {
            "discord_user_id": author.discord_user_id if author else None,
            "discord_username": author.discord_username if author else None,
            "rsn": author.rsn if author else None,
            "avatar": author.discord_avatar_url if author else None,
        } if author else None,
        "collaborators": collaborators,
    }


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
        category_id=category_id, slug=slug, title=title, body=body.body,
        created_by=int(current_user["sub"]), created_at=now, updated_at=now,
    )
    session.add(entry)
    await session.commit()
    return {
        "id": str(entry.id), "title": entry.title, "slug": entry.slug,
        "category_id": str(entry.category_id),
    }
