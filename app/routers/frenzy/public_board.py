"""The public board of the running frenzy event: its tiers, cards and goals."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FrenzyEvent, FrenzyTemplate
from app.dependencies import get_session

router = APIRouter()


@router.get("/active/board")
async def get_active_board(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the active event's tiers, activities, milestones and multipliers."""
    template = (
        await session.execute(
            select(FrenzyTemplate)
            .join(FrenzyEvent, FrenzyEvent.template_id == FrenzyTemplate.id)
            .where(FrenzyEvent.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(404, "No active frenzy event.")
    return {
        "tiers": template.tiers,
        "activities": template.activities,
        "milestones": template.milestones,
        "multipliers": template.multipliers,
    }
