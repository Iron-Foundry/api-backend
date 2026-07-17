from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_session

from ._profile_helpers import PlayerProfileSchema, get_player_profile

router = APIRouter()


@router.get("/player/{rsn}/profile", response_model=PlayerProfileSchema)
async def get_player_profile_route(
    rsn: str, session: AsyncSession = Depends(get_session)
) -> PlayerProfileSchema:
    """Aggregate profile for hover cards: join date, per-account rankings, badges, latest achievement."""
    profile = await get_player_profile(rsn, session)
    if profile is None:
        raise HTTPException(404, "Player not found")
    return profile
