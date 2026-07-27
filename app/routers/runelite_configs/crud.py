from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RuneLiteConfig
from app.dependencies import get_current_user, get_session

from ._helpers import (
    RuneLiteConfigBody,
    require_permission,
    serialize_config,
    validate_config_data,
)

router = APIRouter()


@router.get("/")
async def list_configs(
    session: AsyncSession = Depends(get_session),
    type: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    query = select(RuneLiteConfig).order_by(RuneLiteConfig.name)
    if type is not None:
        query = query.where(RuneLiteConfig.type == type)
    result = await session.execute(query)
    return [serialize_config(c) for c in result.scalars()]


@router.post("/")
async def create_config(
    body: RuneLiteConfigBody,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await require_permission(current_user, "create", session)
    validate_config_data(body.type, body.data)
    now = datetime.now(UTC)
    uid = int(current_user["sub"])
    config = RuneLiteConfig(
        id=uuid.uuid4(),
        type=body.type.strip(),
        name=body.name.strip(),
        description=body.description.strip(),
        data=body.data,
        created_at=now,
        updated_at=now,
        created_by=uid,
        updated_by=uid,
    )
    session.add(config)
    await session.commit()
    return serialize_config(config)


@router.put("/{config_id}")
async def update_config(
    config_id: UUID,
    body: RuneLiteConfigBody,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await require_permission(current_user, "edit", session)
    validate_config_data(body.type, body.data)
    result = await session.execute(
        select(RuneLiteConfig).where(RuneLiteConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "Config not found.")
    config.type = body.type.strip()
    config.name = body.name.strip()
    config.description = body.description.strip()
    config.data = body.data
    config.updated_at = datetime.now(UTC)
    config.updated_by = int(current_user["sub"])
    await session.commit()
    return serialize_config(config)


@router.delete("/{config_id}")
async def delete_config(
    config_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await require_permission(current_user, "delete", session)
    result = await session.execute(
        select(RuneLiteConfig).where(RuneLiteConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "Config not found.")
    await session.delete(config)
    await session.commit()
    return {"ok": True}


@router.get("/{config_id}")
async def get_config(
    config_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await session.execute(
        select(RuneLiteConfig).where(RuneLiteConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(404, "Config not found.")
    return serialize_config(config)
