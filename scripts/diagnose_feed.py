"""Diagnose why a user's activity feed is blank.

Shows event counts by type, user_id linkage, and whether events exist
for each linked RSN.

Run with:
    DATABASE_URL=... uv run python scripts/diagnose_feed.py --rsn "PlayerName"
    DATABASE_URL=... uv run python scripts/diagnose_feed.py --user-id 123456789
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def run(rsn: str | None, discord_user_id: int | None) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL environment variable is not set")
    if not rsn and not discord_user_id:
        sys.exit("Provide --rsn <name> or --user-id <id>")

    engine = create_async_engine(url, echo=False)

    async with engine.connect() as conn:

        # --- Resolve identity ---
        if discord_user_id:
            row = (await conn.execute(
                text("SELECT discord_user_id, rsn FROM users WHERE discord_user_id = :id"),
                {"id": discord_user_id},
            )).mappings().one_or_none()
        else:
            row = (await conn.execute(
                text("SELECT discord_user_id, rsn FROM users WHERE lower(rsn) = lower(:rsn)"),
                {"rsn": rsn},
            )).mappings().one_or_none()

        if not row:
            print("User not found in users table.")
            await engine.dispose()
            return

        uid = row["discord_user_id"]
        primary_rsn = row["rsn"]
        print(f"\n=== User: discord_user_id={uid}  users.rsn={primary_rsn!r} ===\n")

        # --- user_accounts ---
        accounts = (await conn.execute(
            text("SELECT rsn, is_primary FROM user_accounts WHERE discord_user_id = :uid ORDER BY is_primary DESC"),
            {"uid": uid},
        )).mappings().all()

        # --- stats_opt_out check ---
        flags = (await conn.execute(
            text("SELECT stats_opt_out FROM users WHERE discord_user_id = :uid"),
            {"uid": uid},
        )).mappings().one_or_none()
        opted_out = flags["stats_opt_out"] if flags else None
        opt_flag = "  !! OPTED OUT - broadcasts silently dropped at ingest" if opted_out else ""
        print(f"stats_opt_out: {opted_out}{opt_flag}\n")

        if accounts:
            print("user_accounts entries:")
            for a in accounts:
                print(f"  rsn={a['rsn']!r}  is_primary={a['is_primary']}")
        else:
            print("user_accounts: EMPTY (no linked RSNs)")

        all_rsns = [a["rsn"] for a in accounts] or ([primary_rsn] if primary_rsn else [])
        print()

        # --- Events by user_id ---
        by_uid = (await conn.execute(
            text("""
                SELECT type, count(*) AS cnt,
                       sum(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) AS unlinked
                FROM events
                WHERE user_id = :uid
                GROUP BY type ORDER BY cnt DESC
            """),
            {"uid": uid},
        )).mappings().all()

        print(f"Events linked by user_id={uid}:")
        if by_uid:
            for r in by_uid:
                print(f"  type={r['type']:<22}  count={r['cnt']}")
        else:
            print("  (none)")
        print()

        # --- Events by player_name for each RSN ---
        for rsn_val in all_rsns:
            by_name = (await conn.execute(
                text("""
                    SELECT type, count(*) AS cnt,
                           sum(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) AS unlinked,
                           sum(CASE WHEN user_id = :uid THEN 1 ELSE 0 END) AS linked_to_user
                    FROM events
                    WHERE lower(player_name) = lower(:rsn)
                    GROUP BY type ORDER BY cnt DESC
                """),
                {"rsn": rsn_val, "uid": uid},
            )).mappings().all()

            print(f"Events by player_name={rsn_val!r}:")
            if by_name:
                for r in by_name:
                    flag = ""
                    if r["unlinked"] > 0:
                        flag += f"  !! {r['unlinked']} have user_id=NULL"
                    if r["linked_to_user"] < r["cnt"] and r["unlinked"] == 0:
                        flag += f"  !! linked to DIFFERENT user"
                    print(f"  type={r['type']:<22}  count={r['cnt']}{flag}")
            else:
                print("  (none - player_name does not match any events)")
            print()

        # --- Fuzzy RSN search across all events ---
        for rsn_val in all_rsns:
            fuzzy = (await conn.execute(
                text("""
                    SELECT DISTINCT player_name, type
                    FROM events
                    WHERE player_name ILIKE :pattern
                    LIMIT 20
                """),
                {"pattern": f"%{rsn_val.replace(' ', '%')}%"},
            )).mappings().all()
            if fuzzy:
                print(f"Fuzzy matches for {rsn_val!r}:")
                for r in fuzzy:
                    print(f"  player_name={r['player_name']!r}  type={r['type']}")
                print()

        # --- League event player names (sample) ---
        league_players = (await conn.execute(
            text("""
                SELECT DISTINCT player_name, count(*) AS cnt
                FROM events
                WHERE type IN ('league_relic', 'league_rank', 'league_area')
                  AND player_name IS NOT NULL
                GROUP BY player_name
                ORDER BY cnt DESC
                LIMIT 30
            """),
        )).mappings().all()

        print("Player names in league events:")
        for r in league_players:
            print(f"  {r['player_name']!r:<25} ({r['cnt']} events)")
        print()

        # --- Overall event type summary ---
        total = (await conn.execute(
            text("SELECT type, count(*) AS cnt FROM events GROUP BY type ORDER BY cnt DESC LIMIT 20"),
        )).mappings().all()

        print("Overall events table (top 20 by type):")
        for r in total:
            print(f"  type={r['type']:<22}  count={r['cnt']}")

    await engine.dispose()


if __name__ == "__main__":
    rsn_arg: str | None = None
    uid_arg: int | None = None
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--rsn" and i + 1 < len(args):
            rsn_arg = args[i + 1]
        elif a == "--user-id" and i + 1 < len(args):
            uid_arg = int(args[i + 1])

    asyncio.run(run(rsn_arg, uid_arg))
