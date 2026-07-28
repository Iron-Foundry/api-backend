from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyEvent, FrenzyTemplate, FrenzyTemplateVersion, User
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import require_page_permission

from ._scoring import _recalculate_tier_points
from .schemas import CalculatePointsBody, TemplateBody

router = APIRouter()

_PERM = Depends(require_page_permission("frenzy", "edit"))


@router.get("/templates")
async def list_templates(
    session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> list[dict[str, Any]]:
    """List every frenzy template with its tier and scoring summary."""
    rows = (
        (
            await session.execute(
                select(FrenzyTemplate).order_by(FrenzyTemplate.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "version_number": t.version_number,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
        }
        for t in rows
    ]


@router.post("/templates", status_code=201)
async def create_template(
    body: TemplateBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a reusable frenzy template that events are built from."""
    now = datetime.now(UTC)
    uid = int(current_user["sub"])
    tmpl = FrenzyTemplate(
        name=body.name,
        description=body.description,
        tiers=body.tiers,
        activities=body.activities,
        milestones=body.milestones,
        multipliers=body.multipliers,
        total_point_cap=body.total_point_cap,
        version_number=1,
        created_by=uid,
        created_at=now,
        updated_at=now,
    )
    session.add(tmpl)
    await session.flush()
    session.add(
        FrenzyTemplateVersion(
            template_id=tmpl.id,
            version_number=1,
            tiers=body.tiers,
            activities=body.activities,
            milestones=body.milestones,
            multipliers=body.multipliers,
            edited_by=uid,
            created_at=now,
        )
    )
    await session.commit()
    return {"id": tmpl.id, "version_number": 1}


@router.get("/templates/{template_id}")
async def get_template(
    template_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict[str, Any]:
    """Return one template with its full tier and task definition."""
    tmpl = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(404, "Template not found.")
    return {
        "id": tmpl.id,
        "name": tmpl.name,
        "description": tmpl.description,
        "tiers": tmpl.tiers,
        "activities": tmpl.activities,
        "milestones": tmpl.milestones,
        "multipliers": tmpl.multipliers,
        "total_point_cap": tmpl.total_point_cap,
        "version_number": tmpl.version_number,
        "created_at": tmpl.created_at.isoformat(),
        "updated_at": tmpl.updated_at.isoformat(),
    }


@router.put("/templates/{template_id}")
async def update_template(
    template_id: int,
    body: TemplateBody,
    session: AsyncSession = Depends(get_session),
    _perm: None = _PERM,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Replace a template's definition, snapshotting the previous version."""
    tmpl = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(404, "Template not found.")

    uid = int(current_user["sub"])
    now = datetime.now(UTC)
    max_ver = (
        await session.execute(
            select(func.max(FrenzyTemplateVersion.version_number)).where(
                FrenzyTemplateVersion.template_id == template_id
            )
        )
    ).scalar_one_or_none()
    next_ver = (max_ver or 0) + 1

    session.add(
        FrenzyTemplateVersion(
            template_id=tmpl.id,
            version_number=next_ver,
            tiers=tmpl.tiers,
            activities=tmpl.activities,
            milestones=tmpl.milestones,
            multipliers=tmpl.multipliers,
            edited_by=uid,
            created_at=now,
        )
    )
    tmpl.name = body.name
    tmpl.description = body.description
    tmpl.tiers = body.tiers
    tmpl.activities = body.activities
    tmpl.milestones = body.milestones
    tmpl.multipliers = body.multipliers
    tmpl.total_point_cap = body.total_point_cap
    tmpl.version_number = next_ver
    tmpl.updated_at = now

    await session.commit()
    return {
        "id": tmpl.id,
        "version_number": tmpl.version_number,
        "updated_at": now.isoformat(),
    }


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict[str, Any]:
    """Delete a template. Refused while events still reference it."""
    event_count = (
        await session.execute(
            select(func.count(FrenzyEvent.id)).where(
                FrenzyEvent.template_id == template_id
            )
        )
    ).scalar_one()
    if event_count > 0:
        raise HTTPException(409, "Template is referenced by one or more events.")

    tmpl = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(404, "Template not found.")
    await session.delete(tmpl)
    await session.commit()
    return {"ok": True}


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
        "edited_by": {
            "discord_user_id": u.discord_user_id,
            "discord_username": u.discord_username,
            "rsn": u.rsn,
            "avatar": u.discord_avatar_url,
        }
        if u
        else None,
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
    tmpl = (
        await session.execute(
            select(FrenzyTemplate).where(FrenzyTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(404, "Template not found.")

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

    uid = int(current_user["sub"])
    now = datetime.now(UTC)
    max_ver = (
        await session.execute(
            select(func.max(FrenzyTemplateVersion.version_number)).where(
                FrenzyTemplateVersion.template_id == template_id
            )
        )
    ).scalar_one_or_none()
    next_ver = (max_ver or 0) + 1

    session.add(
        FrenzyTemplateVersion(
            template_id=tmpl.id,
            version_number=next_ver,
            tiers=tmpl.tiers,
            activities=tmpl.activities,
            milestones=tmpl.milestones,
            multipliers=tmpl.multipliers,
            edited_by=uid,
            created_at=now,
        )
    )
    tmpl.tiers = ver.tiers
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


@router.post("/calculate-points")
async def calculate_points(
    body: CalculatePointsBody,
    _perm: None = _PERM,
) -> dict[str, Any]:
    """Preview the per-tier point split for a tier set and total cap.

    Pure calculation helper for the template editor; it persists nothing.
    """
    return {"tiers": _recalculate_tier_points(body.tiers, body.total_point_cap)}
