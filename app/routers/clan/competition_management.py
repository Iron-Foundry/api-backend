from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from valkey.asyncio import Valkey

from app.dependencies import get_valkey
from app.services.competitions import (
    CreateCompetitionInput,
    EditCompetitionInput,
    create_competition,
    delete_competition,
    edit_competition,
)
from app.services.http import WiseOldManHandler
from app.services.page_permissions import require_page_permission

from ._comp_cache import _invalidate_competitions_cache
from ._constants import (
    _WOM_API_KEY,
    _WOM_DISCORD_CONTACT,
    _WOM_GROUP_ID,
    _WOM_GROUP_KEY,
)
from ._helpers import _handle_wom_error

router = APIRouter()


@router.post(
    "/competitions",
    status_code=201,
    dependencies=[Depends(require_page_permission("staff.competitions", "create"))],
)
async def create_competition_endpoint(
    body: CreateCompetitionInput,
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> dict[str, Any]:
    """Create a WiseOldMan competition for the clan and announce it."""
    if not _WOM_GROUP_KEY:
        raise HTTPException(503, "WOM group key not configured.")
    try:
        result = await create_competition(
            body,
            group_id=_WOM_GROUP_ID,
            group_key=_WOM_GROUP_KEY,
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
        )
        background_tasks.add_task(_invalidate_competitions_cache, valkey)
        return result.get("competition", result)
    except httpx.HTTPStatusError as exc:
        _handle_wom_error(exc)


@router.put(
    "/competitions/{competition_id}",
    dependencies=[Depends(require_page_permission("staff.competitions", "edit"))],
)
async def edit_competition_endpoint(
    competition_id: int,
    body: EditCompetitionInput,
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> dict[str, Any]:
    """Edit a WiseOldMan competition's title, metric, or window."""
    if not _WOM_GROUP_KEY:
        raise HTTPException(503, "WOM group key not configured.")
    try:
        result = await edit_competition(
            competition_id,
            body,
            group_key=_WOM_GROUP_KEY,
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
        )
        WiseOldManHandler._comp_cache.pop(competition_id, None)
        background_tasks.add_task(_invalidate_competitions_cache, valkey)
        return result
    except httpx.HTTPStatusError as exc:
        _handle_wom_error(exc)


@router.delete(
    "/competitions/{competition_id}",
    status_code=204,
    dependencies=[Depends(require_page_permission("staff.competitions", "delete"))],
)
async def delete_competition_endpoint(
    competition_id: int,
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> None:
    """Delete a WiseOldMan competition and its cached standings."""
    if not _WOM_GROUP_KEY:
        raise HTTPException(503, "WOM group key not configured.")
    try:
        await delete_competition(
            competition_id,
            group_key=_WOM_GROUP_KEY,
            api_key=_WOM_API_KEY,
            discord_contact=_WOM_DISCORD_CONTACT,
        )
        WiseOldManHandler._comp_cache.pop(competition_id, None)
        background_tasks.add_task(_invalidate_competitions_cache, valkey)
    except httpx.HTTPStatusError as exc:
        _handle_wom_error(exc)
