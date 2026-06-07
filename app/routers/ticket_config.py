"""Ticket type configuration - per-type display, behaviour, welcome text and images."""

from __future__ import annotations

import base64
import json
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from valkey.asyncio import Valkey

from app.db.models import Config
from app.dependencies import get_current_user, get_session, get_valkey
from app.services.page_permissions import require_page_permission

router = APIRouter(prefix="/tickets", tags=["ticket-config"])

_DISCORD_GUILD_ID = int(os.getenv("GUILD_ID", "0"))
_TICKET_KEY = "ticket"
_VALKEY_CHANNEL = "ticket:config:refresh"
_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB

_KNOWN_TYPES = ["general", "rankup", "join_cc", "contact_mentor", "sensitive"]
_IMAGE_ALLOWED_TYPES = set(_KNOWN_TYPES) | {"panel"}

_DEFAULTS: dict[str, dict] = {
    "general": {
        "display_name": "General Support",
        "description": "General questions and miscellaneous requests.",
        "emoji": "💬",
        "color_hex": "#5865F2",
        "enabled": True,
        "max_open_per_user": 1,
        "welcome_text": "",
    },
    "rankup": {
        "display_name": "Rank Up",
        "description": "Apply for a rank based on your OSRS achievements.",
        "emoji": "⬆️",
        "color_hex": "#f0b232",
        "enabled": True,
        "max_open_per_user": 1,
        "welcome_text": "",
    },
    "join_cc": {
        "display_name": "Join the CC",
        "description": "Apply to join the Iron Foundry clan chat.",
        "emoji": "🏰",
        "color_hex": "#57f287",
        "enabled": True,
        "max_open_per_user": 1,
        "welcome_text": "",
    },
    "contact_mentor": {
        "display_name": "Contact a Mentor",
        "description": "Get help from a mentor with Raids & PVM.",
        "emoji": "⚔️",
        "color_hex": "#9b59b6",
        "enabled": True,
        "max_open_per_user": 1,
        "welcome_text": "",
    },
    "sensitive": {
        "display_name": "Sensitive",
        "description": "For sensitive matters requiring Senior Staff or Owner attention.",
        "emoji": "🔒",
        "color_hex": "#ed4245",
        "enabled": True,
        "max_open_per_user": 1,
        "welcome_text": "",
    },
}


# ── Pydantic models ───────────────────────────────────────────────────────────


class TicketTypeConfigPatch(BaseModel):
    display_name: str | None = None
    description: str | None = None
    emoji: str | None = None
    color_hex: str | None = None
    enabled: bool | None = None
    max_open_per_user: int | None = None
    welcome_text: str | None = None


class ImageInfo(BaseModel):
    name: str
    filename: str


class TicketTypeConfigOut(BaseModel):
    type_id: str
    display_name: str
    description: str
    emoji: str
    color_hex: str
    enabled: bool
    max_open_per_user: int
    welcome_text: str
    images: list[ImageInfo]


class PanelConfigOut(BaseModel):
    images: list[ImageInfo]


# ── DB helpers ────────────────────────────────────────────────────────────────


async def _get_ticket_row(session: AsyncSession) -> dict:
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _DISCORD_GUILD_ID,
            Config.key == _TICKET_KEY,
        )
    )
    return dict(result.scalar_one_or_none() or {})


async def _set_ticket_row(value: dict, session: AsyncSession) -> None:
    stmt = (
        pg_insert(Config)
        .values(guild_id=_DISCORD_GUILD_ID, key=_TICKET_KEY, value=value)
        .on_conflict_do_update(
            index_elements=["guild_id", "key"],
            set_={"value": value},
        )
    )
    await session.execute(stmt)
    await session.commit()


def _merge(type_id: str, row: dict) -> dict:
    overrides = row.get("type_configs", {}).get(type_id, {})
    return {**_DEFAULTS[type_id], **overrides}


def _images(type_id: str, row: dict) -> list[ImageInfo]:
    prefix = f"{type_id}_img_"
    return [
        ImageInfo(name=key[len(prefix) : -len("_filename")], filename=row[key])
        for key in sorted(row)
        if key.startswith(prefix) and key.endswith("_filename")
    ]


def _build_response(type_id: str, row: dict) -> TicketTypeConfigOut:
    cfg = _merge(type_id, row)
    return TicketTypeConfigOut(
        type_id=type_id,
        display_name=cfg["display_name"],
        description=cfg["description"],
        emoji=cfg["emoji"],
        color_hex=cfg["color_hex"],
        enabled=bool(cfg["enabled"]),
        max_open_per_user=int(cfg["max_open_per_user"]),
        welcome_text=cfg["welcome_text"],
        images=_images(type_id, row),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/config",
    dependencies=[Depends(get_current_user)],
)
async def list_ticket_configs(
    session: AsyncSession = Depends(get_session),
) -> list[TicketTypeConfigOut]:
    row = await _get_ticket_row(session)
    return [_build_response(t, row) for t in _KNOWN_TYPES]


@router.get(
    "/config/panel",
    dependencies=[Depends(get_current_user)],
)
async def get_panel_config(
    session: AsyncSession = Depends(get_session),
) -> PanelConfigOut:
    row = await _get_ticket_row(session)
    return PanelConfigOut(images=_images("panel", row))


@router.get(
    "/config/{type_id}",
    dependencies=[Depends(get_current_user)],
)
async def get_ticket_config(
    type_id: str,
    session: AsyncSession = Depends(get_session),
) -> TicketTypeConfigOut:
    if type_id not in _KNOWN_TYPES:
        raise HTTPException(404, f"Unknown ticket type: {type_id}")
    row = await _get_ticket_row(session)
    return _build_response(type_id, row)


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
    row = await _get_ticket_row(session)
    type_configs: dict = dict(row.get("type_configs", {}))
    existing = _merge(type_id, row)
    patch = body.model_dump(exclude_none=True)
    type_configs[type_id] = {**existing, **patch}
    row = {**row, "type_configs": type_configs}
    await _set_ticket_row(row, session)
    await valkey.publish(_VALKEY_CHANNEL, json.dumps({"type_id": type_id}))
    return _build_response(type_id, row)


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
    if file.content_type not in {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }:
        raise HTTPException(400, "Only JPEG, PNG, WebP or GIF images allowed")
    data = await file.read(_MAX_IMAGE_BYTES + 1)
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image exceeds 8 MB limit")
    filename = file.filename or f"{name}.png"
    row = await _get_ticket_row(session)
    row = {
        **row,
        f"{type_id}_img_{name}_data": base64.b64encode(data).decode(),
        f"{type_id}_img_{name}_filename": filename,
    }
    await _set_ticket_row(row, session)
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
    row = await _get_ticket_row(session)
    drop = {f"{type_id}_img_{name}_data", f"{type_id}_img_{name}_filename"}
    row = {k: v for k, v in row.items() if k not in drop}
    await _set_ticket_row(row, session)
    await valkey.publish(_VALKEY_CHANNEL, json.dumps({"type_id": type_id}))
