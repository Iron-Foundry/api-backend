"""Reusable error responses so the reference documents more than the 200 case.

Attach these to a router rather than an endpoint - `APIRouter(responses=...)`
merges the entry into every route the router carries, so one line documents a
whole feature area. FastAPI still merges per-endpoint `responses=` on top for
the cases a single route adds.
"""

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """The body FastAPI returns for a raised `HTTPException`."""

    detail: str = Field(examples=["Invalid token"])


_UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    401: {
        "model": ErrorDetail,
        "description": (
            "Credentials are missing, malformed, expired, or have been revoked."
        ),
    }
}

_FORBIDDEN: dict[int | str, dict[str, Any]] = {
    403: {
        "model": ErrorDetail,
        "description": (
            "Authenticated, but the caller's Discord roles do not grant this action."
        ),
    }
}

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {
        "model": ErrorDetail,
        "description": "No record matches the identifier in the path.",
    }
}

_BAD_GATEWAY: dict[int | str, dict[str, Any]] = {
    502: {
        "model": ErrorDetail,
        "description": "The internal service behind this proxy did not respond.",
    }
}

_UPSTREAM: dict[int | str, dict[str, Any]] = {
    503: {
        "model": ErrorDetail,
        "description": (
            "An upstream dependency (WiseOldMan, Discord, or the cache service) "
            "is unavailable or has not finished its first sync."
        ),
    }
}

AUTHENTICATED = _UNAUTHORIZED
"""Any endpoint behind a JWT or an API key."""

AUTHENTICATED_LOOKUP = _UNAUTHORIZED | _NOT_FOUND
"""Authenticated, and addresses a single record by id."""

STAFF = _UNAUTHORIZED | _FORBIDDEN
"""Authenticated and role-gated."""

STAFF_LOOKUP = _UNAUTHORIZED | _FORBIDDEN | _NOT_FOUND
"""Role-gated, and addresses a single record by id."""

PUBLIC_LOOKUP = _NOT_FOUND
"""Unauthenticated, but addresses a single record by id."""

PUBLIC_UPSTREAM = _NOT_FOUND | _UPSTREAM
"""Unauthenticated, backed by a scheduled sync from a third party."""

PROXIED = _NOT_FOUND | _BAD_GATEWAY
"""Unauthenticated, and forwarded to an internal service."""
