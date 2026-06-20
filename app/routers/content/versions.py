from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentCollaborator, ContentEntry, ContentEntryVersion, User
from app.dependencies import get_current_user, get_session

from ._helpers import _require_mentor, _validate_page_type

router = APIRouter()


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
            }
            if u
            else None,
        }
        for v, u in result.all()
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
        .where(
            ContentEntryVersion.id == version_id,
            ContentEntryVersion.entry_id == entry_id,
        )
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
        }
        if u
        else None,
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

    entry = (
        await session.execute(select(ContentEntry).where(ContentEntry.id == entry_id))
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "Entry not found.")

    ver = (
        await session.execute(
            select(ContentEntryVersion).where(
                ContentEntryVersion.id == version_id,
                ContentEntryVersion.entry_id == entry_id,
            )
        )
    ).scalar_one_or_none()
    if ver is None:
        raise HTTPException(404, "Version not found.")

    uid = int(current_user["sub"])
    now = datetime.now(timezone.utc)
    entry.title = ver.title
    entry.body = ver.body
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
    updated_at = entry.updated_at
    return {
        "id": str(entry.id),
        "title": entry.title,
        "slug": entry.slug,
        "updated_at": updated_at.isoformat() if updated_at is not None else None,
    }
