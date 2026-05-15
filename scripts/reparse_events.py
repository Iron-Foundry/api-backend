"""Reparse events that were stored with incomplete data or as unknown.

Targets three cases:
  1. type='unknown'       - messages that now parse correctly after pattern fixes
  2. type='combat_achievement' - missing 'difficulty' key in data JSONB
  3. type='personal_best'      - missing 'variant', or 'activity' embeds the variant

Only 'type', 'player_name', and 'data' are ever updated. 'timestamp', 'id',
'sender', and 'is_league_world' are never touched.

Run with:
    DATABASE_URL=... uv run python scripts/reparse_events.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import parser as p

_FETCH_SQL = text(
    """
    SELECT id, type, player_name, raw_message, data
    FROM events
    WHERE raw_message IS NOT NULL
      AND type IN ('unknown', 'combat_achievement', 'personal_best')
    ORDER BY id
    """
)

_UPDATE_SQL = text(
    """
    UPDATE events
    SET type = :type, player_name = :player_name, data = :data
    WHERE id = :id
    """
)

_DELETE_SQL = text("DELETE FROM events WHERE id = :id")

_LINK_USER_IDS_SQL = text(
    """
    UPDATE events e
    SET user_id = u.discord_user_id
    FROM user_accounts u
    WHERE lower(e.player_name) = lower(u.rsn)
      AND e.user_id IS NULL
      AND e.player_name IS NOT NULL
    """
)


def _reparse_row(
    row_type: str, raw_message: str, stored_data: dict
) -> tuple[str, str | None, dict] | None:
    """Return (new_type, new_player_name, new_data) if the row needs updating, else None."""
    kind = p.classify(raw_message)

    if kind == p.BroadcastType.COMBAT_ACHIEVEMENT:
        parsed = p.parse_achievement(raw_message)
        if not parsed:
            return None
        new_data: dict = {
            "achievement_type": parsed.kind,
            "name": parsed.name,
        }
        if parsed.difficulty:
            new_data["difficulty"] = parsed.difficulty
        if (
            row_type != parsed.kind
            or stored_data.get("name") != parsed.name
            or stored_data.get("difficulty") != new_data.get("difficulty")
        ):
            return parsed.kind, parsed.player_name, new_data

    elif kind == p.BroadcastType.PERSONAL_BEST:
        parsed = p.parse_personal_best(raw_message)
        if not parsed:
            return None
        new_data = {
            "activity": parsed.activity,
            "time_seconds": parsed.time_seconds,
            "variant": parsed.variant,
        }
        if (
            row_type != "personal_best"
            or stored_data.get("activity") != parsed.activity
            or stored_data.get("variant") != parsed.variant
        ):
            return "personal_best", parsed.player_name, new_data

    elif kind not in (p.BroadcastType.UNKNOWN, p.BroadcastType.CHAT):
        # Previously unknown message now classifies - parse and store
        dispatch = {
            p.BroadcastType.QUEST: p.parse_achievement,
            p.BroadcastType.DIARY: p.parse_achievement,
            p.BroadcastType.LEVEL_UP: p.parse_level_up,
            p.BroadcastType.XP_MILESTONE: p.parse_xp_milestone,
            p.BroadcastType.PET: p.parse_pet,
            p.BroadcastType.NEW_MEMBER: p.parse_new_member,
            p.BroadcastType.COLLECTION_LOG: p.parse_collection_log,
            p.BroadcastType.LOOT_KEY: p.parse_loot_key,
            p.BroadcastType.CLUE_ITEM: p.parse_clue_item,
            p.BroadcastType.PK: p.parse_pk,
            p.BroadcastType.COFFER_DONATION: p.parse_coffer_transaction,
            p.BroadcastType.COFFER_WITHDRAWAL: p.parse_coffer_transaction,
            p.BroadcastType.HCIM_DEATH: p.parse_hcim_death,
            p.BroadcastType.LOOT: p.parse_loot,
            p.BroadcastType.LEAGUE_RELIC: p.parse_league_relic,
            p.BroadcastType.LEAGUE_RANK: p.parse_league_rank,
            p.BroadcastType.LEAGUE_AREA: p.parse_league_area,
        }
        parse_fn = dispatch.get(kind)
        if not parse_fn:
            return None
        parsed = parse_fn(raw_message)  # type: ignore[arg-type]
        if not parsed:
            return None
        # Build data dict from parsed fields (exclude player_name)
        import dataclasses

        new_data = {
            k: v for k, v in dataclasses.asdict(parsed).items() if k != "player_name"
        }
        player = getattr(parsed, "player_name", None)
        return kind.value, player, new_data

    return None


async def run(dry_run: bool) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL environment variable is not set")

    engine = create_async_engine(url, echo=False)

    async with engine.connect() as conn:
        result = await conn.execute(_FETCH_SQL)
        rows = result.mappings().all()

    if not rows:
        print("No candidate events found.")
        await engine.dispose()
        return

    print(f"Inspecting {len(rows)} events...")

    updates: list[dict] = []
    for row in rows:
        change = _reparse_row(row["type"], row["raw_message"], row["data"] or {})
        if change is None:
            continue
        new_type, new_player, new_data = change
        updates.append(
            {
                "id": row["id"],
                "type": new_type,
                "player_name": new_player,
                "data": json.dumps(new_data),
            }
        )
        if dry_run:
            print(
                f"  [{row['id']}] {row['type']} -> {new_type} | "
                f"player={new_player} | data={new_data}"
            )

    if not updates:
        print("Nothing to update.")
        await engine.dispose()
        return

    print(f"{'Would update' if dry_run else 'Updating'} {len(updates)} event(s).")

    if not dry_run:
        updated = 0
        deleted = 0
        for u in updates:
            try:
                async with engine.begin() as conn:
                    await conn.execute(_UPDATE_SQL, u)
                updated += 1
            except Exception as exc:
                if "unique" in str(exc).lower():
                    # A correctly classified row already exists with the same dedup key.
                    # The unknown duplicate is safe to drop.
                    async with engine.begin() as conn:
                        await conn.execute(_DELETE_SQL, {"id": u["id"]})
                    deleted += 1
                else:
                    raise
        print(f"Updated {updated}, deleted {deleted} duplicate(s).")

        async with engine.begin() as conn:
            result = await conn.execute(_LINK_USER_IDS_SQL)
            print(f"Linked user_id for {result.rowcount} event(s).")

    await engine.dispose()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(run(dry_run))
