from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends
from loguru import logger
from valkey.asyncio import Valkey

from app.dependencies import get_valkey
from app.services.http import WiseOldManHandler, WomPriority

from ._constants import _NC_FRESH_KEY, _NC_FRESH_TTL, _NC_LOCK_KEY, _NC_LOCK_TTL, _NC_STALE_KEY, _NC_STALE_TTL, _WOM_API_KEY, _WOM_DISCORD_CONTACT, _WOM_GROUP_ID

router = APIRouter()


async def _build_name_changes_cache(valkey: Valkey) -> None:
    logger.info("name-changes cache: hydrating from WOM (group={})", _WOM_GROUP_ID)
    try:
        wom = WiseOldManHandler(api_key=_WOM_API_KEY, discord_contact=_WOM_DISCORD_CONTACT, priority=WomPriority.NORMAL)
        changes = await wom.get_group_name_changes(_WOM_GROUP_ID, limit=50)
        result = [
            {"old_name": c["oldName"], "new_name": c["newName"], "resolved_at": c.get("resolvedAt")}
            for c in changes if c.get("status") == "approved"
        ]
        payload = json.dumps(result)
        await valkey.setex(_NC_FRESH_KEY, _NC_FRESH_TTL, payload)
        await valkey.setex(_NC_STALE_KEY, _NC_STALE_TTL, payload)
        logger.info("name-changes cache: wrote {} approved changes", len(result))
    except Exception as exc:
        logger.error("name-changes cache: hydration failed - {}", exc)
    finally:
        await valkey.delete(_NC_LOCK_KEY)


@router.get("/name-changes")
async def group_name_changes(
    background_tasks: BackgroundTasks,
    valkey: Valkey = Depends(get_valkey),
) -> list[dict]:
    """Return recent approved WOM name changes. Stale-while-revalidate, 15 min fresh / 6 h stale."""
    fresh = await valkey.get(_NC_FRESH_KEY)
    if fresh:
        return json.loads(fresh)

    if await valkey.set(_NC_LOCK_KEY, "1", ex=_NC_LOCK_TTL, nx=True):
        logger.info("name-changes: cache miss - scheduling hydration")
        background_tasks.add_task(_build_name_changes_cache, valkey)
    else:
        logger.debug("name-changes: cache miss, hydration already scheduled")

    stale = await valkey.get(_NC_STALE_KEY)
    return json.loads(stale) if stale else []
