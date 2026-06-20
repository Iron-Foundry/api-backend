from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentCollaborator, ContentEntry, ContentEntryVersion
from app.dependencies import get_current_user, get_session

from ._helpers import (
    _require_mentor,
    _require_senior_mod,
    _slug_exists_in_page_type,
    _slugify,
    _validate_page_type,
)

router = APIRouter()


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

    entry = (
        await session.execute(select(ContentEntry).where(ContentEntry.id == entry_id))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Entry not found.")

    fields = body.model_fields_set
    content_fields_check = fields - {"sort_order", "expected_updated_at"}
    if (
        content_fields_check
        and body.expected_updated_at is not None
        and entry.updated_at is not None
    ):

        def _to_utc(dt: datetime) -> datetime:
            return (
                dt.replace(tzinfo=timezone.utc)
                if dt.tzinfo is None
                else dt.astimezone(timezone.utc)
            )

        if _to_utc(body.expected_updated_at).replace(microsecond=0) != _to_utc(
            entry.updated_at
        ).replace(microsecond=0):
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
            if await _slug_exists_in_page_type(
                new_slug, page_type, session, exclude_entry_id=entry_id
            ):
                raise HTTPException(
                    409,
                    f"An entry with slug '{new_slug}' already exists under {page_type}.",
                )
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
            select(func.max(ContentEntryVersion.version_number)).where(
                ContentEntryVersion.entry_id == entry_id
            )
        )
        next_ver = (max_ver_result.scalar_one_or_none() or 0) + 1
        session.add(
            ContentEntryVersion(
                entry_id=entry.id,
                version_number=next_ver,
                title=entry.title,
                body=entry.body,
                edited_by=uid,
                created_at=now,
            )
        )

        if entry.created_by != uid:
            await session.execute(
                pg_insert(ContentCollaborator)
                .values(entry_id=entry.id, discord_user_id=uid, added_at=now)
                .on_conflict_do_nothing()
            )

    await session.commit()
    return {
        "id": str(entry.id),
        "title": entry.title,
        "slug": entry.slug,
        "updated_at": entry.updated_at.isoformat()
        if entry.updated_at is not None
        else None,
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

    entry = (
        await session.execute(select(ContentEntry).where(ContentEntry.id == entry_id))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Entry not found.")

    uid = int(current_user["sub"])
    now = datetime.now(timezone.utc)
    entry.deprecated = True
    entry.deprecated_at = now
    entry.deprecated_by = uid
    await session.commit()
    return {"ok": True}


@router.post("/{page_type}/entries/{entry_id}/restore")
async def restore_entry(
    page_type: str,
    entry_id: UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _validate_page_type(page_type)
    await _require_mentor(current_user, session)

    entry = (
        await session.execute(select(ContentEntry).where(ContentEntry.id == entry_id))
    ).scalar_one_or_none()
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

    entry = (
        await session.execute(select(ContentEntry).where(ContentEntry.id == entry_id))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Entry not found.")

    await session.delete(entry)
    await session.commit()
    return {"ok": True}
