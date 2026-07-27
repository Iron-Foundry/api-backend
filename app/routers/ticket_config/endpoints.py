from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.dependencies import get_current_user, get_session, get_valkey
from app.services.page_permissions import require_page_permission

from ._helpers import (
    _IMAGE_ALLOWED_TYPES,
    _KNOWN_TYPES,
    _MAX_IMAGE_BYTES,
    _VALKEY_CHANNEL,
    ImageInfo,
    PanelConfigOut,
    TicketTypeConfigOut,
    TicketTypeConfigPatch,
    build_response,
    get_images,
    get_ticket_row,
    merge_config,
    set_ticket_row,
)

router = APIRouter()


@router.get("/config", dependencies=[Depends(get_current_user)])
async def list_ticket_configs(
    session: AsyncSession = Depends(get_session),
) -> list[TicketTypeConfigOut]:
    row = await get_ticket_row(session)
    return [build_response(t, row) for t in _KNOWN_TYPES]


@router.get("/config/panel", dependencies=[Depends(get_current_user)])
async def get_panel_config(
    session: AsyncSession = Depends(get_session),
) -> PanelConfigOut:
    row = await get_ticket_row(session)
    return PanelConfigOut(images=get_images("panel", row))


@router.get("/config/{type_id}", dependencies=[Depends(get_current_user)])
async def get_ticket_config(
    type_id: str, session: AsyncSession = Depends(get_session)
) -> TicketTypeConfigOut:
    if type_id not in _KNOWN_TYPES:
        raise HTTPException(404, f"Unknown ticket type: {type_id}")
    row = await get_ticket_row(session)
    return build_response(type_id, row)


@router.patch(
    "/config/{type_id}",
    dependencies=[Depends(require_page_permission("staff.ticket-config", "edit"))],
)
async def patch_ticket_config(
    type_id: str,
    body: TicketTypeConfigPatch,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> TicketTypeConfigOut:
    if type_id not in _KNOWN_TYPES:
        raise HTTPException(404, f"Unknown ticket type: {type_id}")
    row = await get_ticket_row(session)
    type_configs: dict[str, Any] = dict(row.get("type_configs", {}))
    type_configs[type_id] = {
        **merge_config(type_id, row),
        **body.model_dump(exclude_none=True),
    }
    row = {**row, "type_configs": type_configs}
    await set_ticket_row(row, session)
    await valkey.publish(_VALKEY_CHANNEL, json.dumps({"type_id": type_id}))
    return build_response(type_id, row)


@router.post(
    "/config/{type_id}/images",
    status_code=201,
    dependencies=[Depends(require_page_permission("staff.ticket-config", "edit"))],
)
async def upload_ticket_image(
    type_id: str,
    name: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> ImageInfo:
    if type_id not in _IMAGE_ALLOWED_TYPES:
        raise HTTPException(404, f"Unknown ticket type: {type_id}")
    if file.content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise HTTPException(400, "Only JPEG, PNG, WebP or GIF images allowed")
    data = await file.read(_MAX_IMAGE_BYTES + 1)
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image exceeds 8 MB limit")
    filename = file.filename or f"{name}.png"
    row = await get_ticket_row(session)
    row = {
        **row,
        f"{type_id}_img_{name}_data": base64.b64encode(data).decode(),
        f"{type_id}_img_{name}_filename": filename,
    }
    await set_ticket_row(row, session)
    await valkey.publish(_VALKEY_CHANNEL, json.dumps({"type_id": type_id}))
    return ImageInfo(name=name, filename=filename)


@router.delete(
    "/config/{type_id}/images/{name}",
    status_code=204,
    dependencies=[Depends(require_page_permission("staff.ticket-config", "delete"))],
)
async def delete_ticket_image(
    type_id: str,
    name: str,
    session: AsyncSession = Depends(get_session),
    valkey: Valkey = Depends(get_valkey),
) -> None:
    if type_id not in _IMAGE_ALLOWED_TYPES:
        raise HTTPException(404, f"Unknown ticket type: {type_id}")
    row = await get_ticket_row(session)
    drop = {f"{type_id}_img_{name}_data", f"{type_id}_img_{name}_filename"}
    row = {k: v for k, v in row.items() if k not in drop}
    await set_ticket_row(row, session)
    await valkey.publish(_VALKEY_CHANNEL, json.dumps({"type_id": type_id}))
