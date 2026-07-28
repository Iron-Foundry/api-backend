"""Deployment identity for the running api-backend process."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.version import VERSION

router = APIRouter(tags=["meta"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, Any]:
    """Report that the process is up. Polled by the container healthcheck."""
    return {"status": "ok"}


class VersionInfo(BaseModel):
    service: str = Field(examples=["api-backend"])
    version: str = Field(examples=["1.0.0"])
    git_sha: str | None = Field(examples=["a9adca9f3c1e4b7d2f08c5619ab3de7741bc0e52"])
    build_time: str | None = Field(examples=["2026-07-28T09:14:22Z"])


@router.get("/version", summary="Report the running build")
async def version() -> VersionInfo:
    """Identify the deployed build.

    `version` comes from the package manifest. `git_sha` and `build_time` are
    injected as container build arguments and are `null` for a local run
    outside Docker.
    """
    return VersionInfo(
        service="api-backend",
        version=VERSION,
        git_sha=os.getenv("GIT_SHA") or None,
        build_time=os.getenv("BUILD_TIME") or None,
    )
