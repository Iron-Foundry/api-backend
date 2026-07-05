from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Annotated, Any, Literal

import httpx
from loguru import logger
from pydantic import BaseModel, BeforeValidator, Field


class DiscordUser(BaseModel):
    id: str
    name: str
    avatarHash: str | None = None


class DinkItem(BaseModel):
    id: int
    quantity: int
    priceEach: int
    name: str


class DinkLocation(BaseModel):
    regionId: int
    plane: int
    instanced: bool


class DinkDeathExtra(BaseModel):
    valueLost: int
    isPvp: bool
    killerName: str | None = None
    killerNpcId: int | None = None
    keptItems: list[DinkItem] = Field(default_factory=list)
    lostItems: list[DinkItem] = Field(default_factory=list)
    location: DinkLocation | None = None


def _coerce_bool(v: Any) -> Any:
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return v


_CoercedBool = Annotated[bool, BeforeValidator(_coerce_bool)]


class DinkDeathNotification(BaseModel):
    content: str = ""
    extra: DinkDeathExtra
    type: Literal["DEATH"]
    playerName: str
    accountType: str
    seasonalWorld: _CoercedBool
    dinkAccountHash: str
    embeds: list[dict[str, Any]] = Field(default_factory=list)
    clanName: str | None = None
    groupIronClanName: str | None = None
    discordUser: DiscordUser | None = None
    world: int | None = None
    regionId: int | None = None


_MENTION_RE = re.compile(r"@(?:everyone|here)|<@[!&]?\d+>")
_URL_RE = re.compile(r"https?://[^\s<>\"]+")


def sanitize_content(text: str) -> str:
    """Strip Discord mentions and URLs from notification content."""
    text = _MENTION_RE.sub("", text)
    return _URL_RE.sub("", text).strip()


_WOM_BASE_URL = "https://api.wiseoldman.net/v2"
_IRONCLAD_GROUP_ID = 1500
_CACHE_TTL_SECONDS = 300.0


class _WomMemberCache:
    def __init__(self) -> None:
        self._members: frozenset[str] = frozenset()
        self._fetched_at: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()

    async def get_members(self) -> frozenset[str]:
        now = time.monotonic()
        if self._members and now - self._fetched_at < _CACHE_TTL_SECONDS:
            return self._members
        async with self._lock:
            now = time.monotonic()
            if self._members and now - self._fetched_at < _CACHE_TTL_SECONDS:
                return self._members
            await self._refresh()
            return self._members

    async def _refresh(self) -> None:
        url = f"{_WOM_BASE_URL}/groups/{_IRONCLAD_GROUP_ID}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
            self._members = frozenset(
                m["player"]["displayName"].lower()
                for m in data.get("memberships", [])
                if m.get("player", {}).get("displayName")
            )
            self._fetched_at = time.monotonic()
            logger.info(
                "ironclad: WOM group {} cache refreshed, {} members",
                _IRONCLAD_GROUP_ID,
                len(self._members),
            )
        except Exception as exc:
            logger.warning("ironclad: WOM cache refresh failed: {}", exc)
            if not self._members:
                raise


ironclad_wom_cache = _WomMemberCache()

_IRONCLAD_WEBHOOK_URL = os.getenv("IRONCLAD_WEBHOOK_URL", "REPLACE_WITH_WEBHOOK_URL")


async def forward_to_webhook(
    notification: DinkDeathNotification,
    image_data: bytes | None,
    image_content_type: str | None,
) -> None:
    """Forward a sanitized Dink death notification to the Ironclad Discord webhook."""
    sanitized = notification.model_copy(
        update={"content": sanitize_content(notification.content)}
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        if image_data is not None:
            resp = await client.post(
                _IRONCLAD_WEBHOOK_URL,
                data={"payload_json": sanitized.model_dump_json()},
                files={
                    "file": ("image", image_data, image_content_type or "image/png")
                },
            )
        else:
            resp = await client.post(
                _IRONCLAD_WEBHOOK_URL,
                json=sanitized.model_dump(),
            )
    resp.raise_for_status()
