"""Migration 0073 points stored OSRSClans image links at Foundry's image route."""

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
    / "0073_osrsclans_images_via_foundry.py"
)
_PUBLIC = "https://api.ironfoundry.cc"
_FOUNDRY = f"{_PUBLIC}/reference/osrs/images"
_OSRSCLANS = "https://osrsclans.cc/api/v1/osrs"


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0073", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _rewrite(engine: AsyncEngine, stored: str, pair: tuple[str, str]) -> str:
    now = datetime.now(UTC)
    tiers = {"t1": {"sources": [{"icon_url": stored, "items": []}]}}
    async with AsyncSession(engine) as session:
        session.add(
            TileRepositoryTile(
                title="x", icon_url=stored, created_at=now, updated_at=now
            )
        )
        session.add(
            FrenzyTemplate(name="x", tiers=tiers, created_at=now, updated_at=now)
        )
        await session.commit()
        for statement in _migration().rewrite_statements(pair):
            await session.execute(statement)
        await session.commit()
        tile = (await session.execute(select(TileRepositoryTile))).scalar_one()
        template = (await session.execute(select(FrenzyTemplate))).scalar_one()
    assert template.tiers["t1"]["sources"][0]["icon_url"] == tile.icon_url
    return tile.icon_url or ""


@pytest.mark.parametrize(
    ("stored", "rewritten"),
    [
        (f"{_OSRSCLANS}/items/4151.webp", f"{_FOUNDRY}/items/4151.webp"),
        (f"{_OSRSCLANS}/npcs/8059.webp", f"{_FOUNDRY}/npcs/8059.webp"),
        (
            f"{_OSRSCLANS}/sprites/197.webp?frame=0",
            f"{_FOUNDRY}/sprites/197.webp?frame=0",
        ),
        (
            "https://oldschool.runescape.wiki/images/Vorkath.png",
            "https://oldschool.runescape.wiki/images/Vorkath.png",
        ),
    ],
)
async def test_stored_links_point_at_foundry(
    seed_engine: AsyncEngine, _truncate: None, stored: str, rewritten: str
) -> None:
    pair = _migration().upgrade_pair(_PUBLIC)
    assert await _rewrite(seed_engine, stored, pair) == rewritten


async def test_downgrade_restores_osrsclans_links(
    seed_engine: AsyncEngine, _truncate: None
) -> None:
    pair = _migration().downgrade_pair(_PUBLIC)
    stored = f"{_FOUNDRY}/items/4151.webp"
    assert await _rewrite(seed_engine, stored, pair) == f"{_OSRSCLANS}/items/4151.webp"
