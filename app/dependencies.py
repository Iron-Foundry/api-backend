import os
from collections.abc import AsyncGenerator
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import User

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
_ALGORITHM = "HS256"
_METRICS_API_KEY = os.getenv("METRICS_API_KEY", "")


def get_valkey(request: Request) -> Valkey:
    return request.app.state.valkey


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession scoped to the request."""
    async with request.app.state.session_factory() as session:
        yield session


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


async def get_optional_user(
    authorization: Optional[str] = Header(default=None),
) -> dict | None:
    """Decode a Bearer JWT if present; return None if no token provided."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer ") :]
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[_ALGORITHM])
    except JWTError:
        return None


async def verify_metrics_key(verification_code: str = Header(...)) -> None:
    """Validate the verification-code header against the METRICS_API_KEY env var."""
    if not _METRICS_API_KEY or verification_code != _METRICS_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid metrics API key")


async def verify_clan(
    verification_code: str = Header(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Resolve a verification-code header to the matching user row in PostgreSQL.

    Returns a dict with ``guild_id`` and ``discord_user_id``.
    Raises 401 if the key does not exist or has been revoked.
    """
    result = await session.execute(
        select(User).where(
            User.api_key == verification_code,
            User.key_is_active == True,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    return {
        "guild_id": user.guild_id,
        "discord_user_id": user.discord_user_id,
        "key": verification_code,
    }
