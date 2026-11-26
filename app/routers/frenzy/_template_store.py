from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyTemplate, FrenzyTemplateVersion, User


async def load_template(session: AsyncSession, template_id: int) -> FrenzyTemplate:
    """Return the template, or raise 404 when it does not exist."""
    tmpl = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(404, "Template not found.")
    return tmpl


async def next_version_number(session: AsyncSession, template_id: int) -> int:
    """Return the version number the template's next snapshot takes."""
    max_ver = (
        await session.execute(
            select(func.max(FrenzyTemplateVersion.version_number)).where(
                FrenzyTemplateVersion.template_id == template_id
            )
        )
    ).scalar_one_or_none()
    return (max_ver or 0) + 1


def snapshot(
    tmpl: FrenzyTemplate, version_number: int, uid: int, now: datetime
) -> FrenzyTemplateVersion:
    """Return a version row that holds the template's current definition."""
    return FrenzyTemplateVersion(
        template_id=tmpl.id,
        version_number=version_number,
        tiers=tmpl.tiers,
        activities=tmpl.activities,
        milestones=tmpl.milestones,
        multipliers=tmpl.multipliers,
        edited_by=uid,
        created_at=now,
    )


def editor_out(u: User | None) -> dict[str, Any] | None:
    """Return the public fields of a version's editor, or None when unknown."""
    if u is None:
        return None
    return {
        "discord_user_id": u.discord_user_id,
        "discord_username": u.discord_username,
        "rsn": u.rsn,
        "avatar": u.discord_avatar_url,
    }
