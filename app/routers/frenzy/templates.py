from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyEvent, FrenzyTemplate
from app.dependencies import get_current_user, get_session
from app.services.page_permissions import require_page_permission

from ._points import assign_item_points
from ._template_store import load_template, next_version_number, snapshot
from .schemas import TemplateBody

router = APIRouter()

_PERM = Depends(require_page_permission("frenzy.admin", "edit"))


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
    """Create a reusable frenzy template. The server sets each item's points."""
    now = datetime.now(UTC)
    uid = int(current_user["sub"])
    tmpl = FrenzyTemplate(
        name=body.name,
        description=body.description,
        tiers=assign_item_points(body.tiers),
        activities=body.activities,
        milestones=body.milestones,
        multipliers=body.multipliers,
        version_number=1,
        created_by=uid,
        created_at=now,
        updated_at=now,
    )
    session.add(tmpl)
    await session.flush()
    session.add(snapshot(tmpl, 1, uid, now))
    await session.commit()
    return {"id": tmpl.id, "version_number": 1}


@router.get("/templates/{template_id}")
async def get_template(
    template_id: int, session: AsyncSession = Depends(get_session), _perm: None = _PERM
) -> dict[str, Any]:
    """Return one template with its full tier and task definition."""
    tmpl = await load_template(session, template_id)
    return {
        "id": tmpl.id,
        "name": tmpl.name,
        "description": tmpl.description,
        "tiers": tmpl.tiers,
        "activities": tmpl.activities,
        "milestones": tmpl.milestones,
        "multipliers": tmpl.multipliers,
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
    """Replace a template's definition. The server sets each item's points."""
    tmpl = await load_template(session, template_id)
    now = datetime.now(UTC)
    next_ver = await next_version_number(session, template_id)
    session.add(snapshot(tmpl, next_ver, int(current_user["sub"]), now))
    tmpl.name = body.name
    tmpl.description = body.description
    tmpl.tiers = assign_item_points(body.tiers)
    tmpl.activities = body.activities
    tmpl.milestones = body.milestones
    tmpl.multipliers = body.multipliers
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

    await session.delete(await load_template(session, template_id))
    await session.commit()
    return {"ok": True}
