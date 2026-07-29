import os
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import User

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
_ALGORITHM = "HS256"
_METRICS_API_KEY = os.getenv("METRICS_API_KEY", "")

bearer_scheme = HTTPBearer(
    scheme_name="DiscordJWT",
    description=(
        "HS256 JWT issued by `GET /auth/callback` after Discord OAuth2, or by "
        "`POST /auth/token` in exchange for a member API key. Send it as "
        "`Authorization: Bearer <token>`."
    ),
    auto_error=False,
)

clan_key_scheme = APIKeyHeader(
    name="verification-code",
    scheme_name="MemberApiKey",
    description=(
        "Per-member API key from `GET /members/me/api-key`, used by the RuneLite "
        "plugin. Revoked keys are rejected."
    ),
    auto_error=False,
)

metrics_key_scheme = APIKeyHeader(
    name="verification-code",
    scheme_name="MetricsApiKey",
    description=(
        "Shared service key (`METRICS_API_KEY`) for service-to-service reporting "
        "from discord-server and discord-utils."
    ),
    auto_error=False,
)


def get_valkey(request: Request) -> Valkey:
    return request.app.state.valkey


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """Yield an AsyncSession scoped to the request."""
    async with request.app.state.session_factory() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict[str, Any]:
    """Decode a Bearer JWT and return its payload.

    Raises 401 if the header is missing, malformed, or the token is invalid.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict[str, Any] | None:
    """Decode a Bearer JWT if present; return None if no token provided."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[_ALGORITHM])
    except JWTError:
        return None


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode a JWT outside the dependency chain, for WebSocket handshakes.

    A browser cannot set an Authorization header on a WebSocket, so the socket
    authenticates with a first frame instead and needs the check as a plain
    function rather than a `Security` dependency.
    """
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[_ALGORITHM])
    except JWTError:
        return None


async def verify_metrics_key(
    verification_code: str | None = Security(metrics_key_scheme),
) -> None:
    """Validate the verification-code header against the METRICS_API_KEY env var."""
    if not _METRICS_API_KEY or verification_code != _METRICS_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid metrics API key")


async def verify_clan(
    verification_code: str | None = Security(clan_key_scheme),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Resolve a verification-code header to the matching user row in PostgreSQL.

    Returns a dict with ``guild_id`` and ``discord_user_id``.
    Raises 401 if the key is absent, does not exist, or has been revoked.
    """
    if not verification_code:
        raise HTTPException(status_code=401, detail="Missing API key")
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
