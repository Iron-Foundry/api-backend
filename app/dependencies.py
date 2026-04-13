import os

from fastapi import Depends, Header, HTTPException, Request
from jose import JWTError, jwt
from pymongo.asynchronous.database import AsyncDatabase
from valkey.asyncio import Valkey

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
_ALGORITHM = "HS256"


def get_db(request: Request) -> AsyncDatabase:
    return request.app.state.db


def get_valkey(request: Request) -> Valkey:
    return request.app.state.valkey


async def get_current_user(authorization: str = Header(...)) -> dict:
    """Decode a Bearer JWT and return its payload.

    Raises 401 if the header is missing, malformed, or the token is invalid.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization[len("Bearer ") :]
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


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
    return {
        "name": doc["guild_name"],
        "discord_user_id": doc["discord_user_id"],
        "key": verification_code,
    }
