from fastapi import Depends, Header, HTTPException, Request
from pymongo.asynchronous.database import AsyncDatabase
from valkey.asyncio import Valkey


def get_db(request: Request) -> AsyncDatabase:
    return request.app.state.db


def get_valkey(request: Request) -> Valkey:
    return request.app.state.valkey


async def verify_clan(
    verification_code: str = Header(...),
    db: AsyncDatabase = Depends(get_db),
) -> dict:
    """Resolve a verification-code header to the matching user key document.

    Returns a dict containing at least ``name`` (the Discord guild name, used
    as the clan identifier in stored events) and ``discord_user_id``.
    Raises 401 if the key does not exist or has been revoked.
    """
    doc = await db["user_keys"].find_one({"key": verification_code, "is_active": True})
    if not doc:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    return {"name": doc["guild_name"], "discord_user_id": doc["discord_user_id"]}
