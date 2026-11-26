"""Migration 0066 rewrites stored osrs-cache image links to OSRSClans images."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import FrenzyTemplate, TileRepositoryTile

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "0066_osrsclans_image_urls.py"
)
_OSRSCLANS = "https://osrsclans.cc/api/v1/osrs"


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0066", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("stored", "rewritten"),
    [
        (
            "https://api.ironfoundry.cc/osrs-cache/item-icons/4151",
            f"{_OSRSCLANS}/items/4151.webp",
        ),
        (
            "http://localhost:8000/osrs-cache/item-icons/995/render?size=256",
            f"{_OSRSCLANS}/items/995.webp",
        ),
        (
            "https://api.ironfoundry.cc/osrs-cache/sprites/197/0?format=png&scale=4",
            f"{_OSRSCLANS}/sprites/197.webp?frame=0",
        ),
        (
            "https://oldschool.runescape.wiki/images/Vorkath.png",
            "https://oldschool.runescape.wiki/images/Vorkath.png",
        ),
    ],
)
async def test_stored_links_point_at_osrsclans(
    seed_engine: AsyncEngine, _truncate: None, stored: str, rewritten: str
) -> None:
    now = datetime.now(UTC)
    tiers = {"t1": {"sources": [{"items": [{"icon_url": stored}]}]}}
    async with AsyncSession(seed_engine) as session:
        session.add(
            TileRepositoryTile(
                title="x", icon_url=stored, created_at=now, updated_at=now
            )
        )
        session.add(
            FrenzyTemplate(name="x", tiers=tiers, created_at=now, updated_at=now)
        )
        await session.commit()
        for statement in _migration().rewrite_statements(_migration().UPGRADE_PAIRS):
            await session.execute(statement)
        await session.commit()
        tile = (await session.execute(select(TileRepositoryTile))).scalar_one()
        template = (await session.execute(select(FrenzyTemplate))).scalar_one()

    assert tile.icon_url == rewritten
    assert template.tiers["t1"]["sources"][0]["items"][0]["icon_url"] == rewritten
