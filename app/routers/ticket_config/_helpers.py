"""Helpers and models for ticket type configuration."""

from __future__ import annotations

import os

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Config

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


async def get_ticket_row(session: AsyncSession) -> dict:
    result = await session.execute(
        select(Config.value).where(
            Config.guild_id == _DISCORD_GUILD_ID, Config.key == _TICKET_KEY
        )
    )
    return dict(result.scalar_one_or_none() or {})


async def set_ticket_row(value: dict, session: AsyncSession) -> None:
    stmt = (
        pg_insert(Config)
        .values(guild_id=_DISCORD_GUILD_ID, key=_TICKET_KEY, value=value)
        .on_conflict_do_update(
            index_elements=["guild_id", "key"], set_={"value": value}
        )
    )
    await session.execute(stmt)
    await session.commit()


def merge_config(type_id: str, row: dict) -> dict:
    overrides = row.get("type_configs", {}).get(type_id, {})
    return {**_DEFAULTS[type_id], **overrides}


def get_images(type_id: str, row: dict) -> list[ImageInfo]:
    prefix = f"{type_id}_img_"
    return [
        ImageInfo(name=key[len(prefix) : -len("_filename")], filename=row[key])
        for key in sorted(row)
        if key.startswith(prefix) and key.endswith("_filename")
    ]


def build_response(type_id: str, row: dict) -> TicketTypeConfigOut:
    cfg = merge_config(type_id, row)
    return TicketTypeConfigOut(
        type_id=type_id,
        display_name=cfg["display_name"],
        description=cfg["description"],
        emoji=cfg["emoji"],
        color_hex=cfg["color_hex"],
        enabled=bool(cfg["enabled"]),
        max_open_per_user=int(cfg["max_open_per_user"]),
        welcome_text=cfg["welcome_text"],
        images=get_images(type_id, row),
    )
