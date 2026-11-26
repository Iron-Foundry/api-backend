from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyTemplateVersion, User
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import require_page_permission

from ._points import assign_item_points
from ._template_store import editor_out, load_template, next_version_number, snapshot

router = APIRouter()

_PERM = Depends(require_page_permission("frenzy.admin", "edit"))


@router.get("/templates/{template_id}/versions")
async def list_template_versions(
    template_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> list[dict[str, Any]]:
    """List a template's saved versions with who authored each."""
    result = await session.execute(
        select(FrenzyTemplateVersion, User)
        .join(
            User, User.discord_user_id == FrenzyTemplateVersion.edited_by, isouter=True
        )
        .where(FrenzyTemplateVersion.template_id == template_id)
        .order_by(FrenzyTemplateVersion.version_number.desc())
    )
    return [
        {
            "id": v.id,
            "version_number": v.version_number,
            "created_at": v.created_at.isoformat(),
            "edited_by": editor_out(u),
        }
        for v, u in result.all()
    ]


@router.get("/templates/{template_id}/versions/{version_id}")
async def get_template_version(
    template_id: int,
    version_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Return one archived version of a template in full."""
    row = (
        await session.execute(
            select(FrenzyTemplateVersion, User)
            .join(
                User,
                User.discord_user_id == FrenzyTemplateVersion.edited_by,
                isouter=True,
            )
            .where(
                FrenzyTemplateVersion.id == version_id,
                FrenzyTemplateVersion.template_id == template_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "Version not found.")
    v, u = row
    return {
        "id": v.id,
        "version_number": v.version_number,
        "tiers": v.tiers,
        "activities": v.activities,
        "milestones": v.milestones,
        "multipliers": v.multipliers,
        "created_at": v.created_at.isoformat(),
        "edited_by": editor_out(u),
    }


@router.post("/templates/{template_id}/revert/{version_id}")
async def revert_template_to_version(
    template_id: int,
    version_id: int,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Restore an archived version as the template's current definition."""
    tmpl = await load_template(session, template_id)
    ver = (
        await session.execute(
            select(FrenzyTemplateVersion).where(
                FrenzyTemplateVersion.id == version_id,
                FrenzyTemplateVersion.template_id == template_id,
            )
        )
    ).scalar_one_or_none()
    if ver is None:
        raise HTTPException(404, "Version not found.")

    now = datetime.now(UTC)
    next_ver = await next_version_number(session, template_id)
    session.add(snapshot(tmpl, next_ver, int(current_user["sub"]), now))
    tmpl.tiers = assign_item_points(ver.tiers)
    tmpl.activities = ver.activities
    tmpl.milestones = ver.milestones
    tmpl.multipliers = ver.multipliers
    tmpl.version_number = next_ver
    tmpl.updated_at = now

    await session.commit()
    return {
        "id": tmpl.id,
        "version_number": tmpl.version_number,
        "updated_at": now.isoformat(),
    }
