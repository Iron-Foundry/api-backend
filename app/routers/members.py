"""Members router — authenticated endpoints for profile self-management."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from app.dependencies import get_current_user, get_db

router = APIRouter(prefix="/members", tags=["members"])

_RSN_RE = re.compile(r"^[A-Za-z0-9 _-]{1,12}$")


# ── request bodies ─────────────────────────────────────────────────────────


class PrivacyUpdate(BaseModel):
    stats_opt_out: bool


class RsnUpdate(BaseModel):
    rsn: str


# ── endpoints ──────────────────────────────────────────────────────────────


@router.patch("/me/privacy")
async def update_privacy(
    body: PrivacyUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    """Toggle stats opt-out for the authenticated user."""
    discord_user_id = int(current_user["sub"])
    await db["users"].update_one(
        {"discord_user_id": discord_user_id},
        {
            "$set": {
                "stats_opt_out": body.stats_opt_out,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    logger.info(
        "members/privacy: user {} set stats_opt_out={}",
        discord_user_id,
        body.stats_opt_out,
    )
    return {"stats_opt_out": body.stats_opt_out}


@router.patch("/me/rsn")
async def update_rsn(
    body: RsnUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    """Update the RSN linked to the authenticated user's account."""
    rsn = body.rsn.strip()
    if not rsn:
        raise HTTPException(status_code=422, detail="RSN cannot be empty.")
    if not _RSN_RE.match(rsn):
        raise HTTPException(
            status_code=422,
            detail="RSN must be 1–12 characters: letters, numbers, spaces, hyphens, underscores.",
        )

    discord_user_id = int(current_user["sub"])

    # Check the RSN isn't already claimed by a different user.
    existing = await db["users"].find_one(
        {"rsn": {"$regex": f"^{re.escape(rsn)}$", "$options": "i"}},
        {"discord_user_id": 1},
    )
    if existing and existing["discord_user_id"] != discord_user_id:
        raise HTTPException(status_code=409, detail="That RSN is linked to another account.")

    await db["users"].update_one(
        {"discord_user_id": discord_user_id},
        {
            "$set": {
                "rsn": rsn,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    logger.info("members/rsn: user {} linked RSN {!r}", discord_user_id, rsn)
    return {"rsn": rsn}
