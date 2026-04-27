"""Fetch all metric views for a WOM team competition and export compact JSON.

Output structure:
    { team_name: { player_name: { metric: gained, ... }, ... }, ... }

Only the "gained" value is kept per player per metric.
Metrics where every participant gained 0 are omitted.

Run with:
    uv run python scripts/fetch_competition.py --comp-id 12345
    uv run python scripts/fetch_competition.py --comp-id 12345 --out results.json
    uv run python scripts/fetch_competition.py --comp-id 12345 --stdout

Environment:
    WOM_API_KEY      (optional) increases rate limits
    WOM_DISCORD      (optional) Discord handle for the User-Agent
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import httpx
from tqdm import tqdm

METRICS: list[str] = [
    # Skills
    "overall", "attack", "defence", "strength", "hitpoints", "ranged", "prayer",
    "magic", "cooking", "woodcutting", "fletching", "fishing", "firemaking",
    "crafting", "smithing", "mining", "herblore", "agility", "thieving", "slayer",
    "farming", "runecrafting", "hunter", "construction", "sailing",
    # Bosses
    "abyssal_sire",
    "alchemical_hydra",
    "amoxliatl",
    "araxxor",
    "artio",
    "barrows_chests",
    "brutus",
    "bryophyta",
    "callisto",
    "calvarion",
    "cerberus",
    "chambers_of_xeric",
    "chambers_of_xeric_challenge_mode",
    "chaos_elemental",
    "chaos_fanatic",
    "commander_zilyana",
    "corporeal_beast",
    "crazy_archaeologist",
    "dagannoth_prime",
    "dagannoth_rex",
    "dagannoth_supreme",
    "deranged_archaeologist",
    "doom_of_mokhaiotl",
    "duke_sucellus",
    "general_graardor",
    "giant_mole",
    "grotesque_guardians",
    "hespori",
    "kalphite_queen",
    "king_black_dragon",
    "kraken",
    "kreearra",
    "kril_tsutsaroth",
    "lunar_chests",
    "nex",
    "nightmare",
    "phosanis_nightmare",
    "obor",
    "phantom_muspah",
    "sarachnis",
    "scorpia",
    "scurrius",
    "shellbane_gryphon",
    "skotizo",
    "sol_heredit",
    "spindel",
    "tempoross",
    "the_gauntlet",
    "the_corrupted_gauntlet",
    "the_hueycoatl",
    "the_leviathan",
    "the_royal_titans",
    "the_whisperer",
    "theatre_of_blood",
    "theatre_of_blood_hard_mode",
    "thermonuclear_smoke_devil",
    "tombs_of_amascut",
    "tombs_of_amascut_expert",
    "tzkal_zuk",
    "tztok_jad",
    "vardorvis",
    "venenatis",
    "vetion",
    "vorkath",
    "wintertodt",
    "yama",
    "zalcano",
    "zulrah",
    # Activities
    "bounty_hunter_hunter", "bounty_hunter_rogue", "clue_scrolls_all",
    "clue_scrolls_beginner", "clue_scrolls_easy", "clue_scrolls_elite",
    "clue_scrolls_hard", "clue_scrolls_master", "clue_scrolls_medium",
    "colosseum_glory", "collections_logged", "guardians_of_the_rift",
    "last_man_standing", "pvp_arena", "soul_wars_zeal",
    # Computed
    "ehp", "ehb",
]

WOM_BASE = "https://api.wiseoldman.net/v2"


async def _get(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: dict[str, str] | None = None,
    bar: "tqdm[str] | None" = None,
) -> dict:
    url = WOM_BASE + path
    for attempt in range(3):
        resp = await client.get(url, params=params)

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "10"))
            if bar:
                bar.set_postfix_str(f"429 — sleeping {retry_after:.0f}s")
            await asyncio.sleep(retry_after)
            continue

        if resp.is_success:
            limit     = resp.headers.get("RateLimit-Limit", "?")
            remaining = resp.headers.get("RateLimit-Remaining", "?")
            reset_in_raw = resp.headers.get("RateLimit-Reset", "0")
            bucket = f"{remaining}/{limit}"

            if bar:
                bar.set_postfix_str(f"bucket {bucket}")

            remaining_int = int(remaining) if remaining != "?" else 100
            if remaining_int <= 1:
                reset_in = float(reset_in_raw)
                sleep_for = max(reset_in, 0.5)
                if bar:
                    bar.set_postfix_str(f"bucket {bucket} — sleeping {sleep_for:.1f}s")
                await asyncio.sleep(sleep_for)
                if bar:
                    bar.set_postfix_str(f"bucket {bucket}")

            return resp.json()

        if bar:
            bar.set_postfix_str(f"HTTP {resp.status_code} attempt {attempt + 1}")
        if attempt < 2:
            await asyncio.sleep(2 ** attempt)

    raise RuntimeError(f"All retries exhausted for {path}")


async def fetch_competition(comp_id: int, api_key: str | None, discord: str | None) -> dict:
    headers: dict[str, str] = {
        "User-Agent": f"IronFoundry/1.0 (discord: @{discord})" if discord else "IronFoundry/1.0",
    }
    if api_key:
        headers["x-api-key"] = api_key

    # team_name -> player_name -> {metric: gained}
    teams: dict[str, dict[str, dict[str, int]]] = {}

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        # Seed teams/players from the base competition fetch
        tqdm.write(f"[{comp_id}] fetching base competition…")
        base = await _get(client, f"/competitions/{comp_id}")
        for p in base.get("participations", []):
            team = p.get("teamName") or "No Team"
            player = p["player"]["displayName"]
            teams.setdefault(team, {}).setdefault(player, {})
        tqdm.write(f"  {len(teams)} teams, {sum(len(v) for v in teams.values())} players seeded")

        with tqdm(METRICS, unit="metric", dynamic_ncols=True, file=sys.stderr) as bar:
            for metric in bar:
                bar.set_description(metric.ljust(40))
                try:
                    data = await _get(
                        client,
                        f"/competitions/{comp_id}",
                        params={"metric": metric},
                        bar=bar,  # type: ignore[arg-type]
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 400:
                        bar.set_postfix_str("skipped (400)")
                        continue
                    bar.set_postfix_str(f"error {exc.response.status_code}")
                    continue
                except Exception as exc:
                    bar.set_postfix_str(f"error: {exc}")
                    continue

                for p in data.get("participations", []):
                    gained = (p.get("progress") or {}).get("gained") or 0
                    if gained:
                        team = p.get("teamName") or "No Team"
                        player = p["player"]["displayName"]
                        teams.setdefault(team, {}).setdefault(player, {})[metric] = gained

    return {
        "competition_id": comp_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "teams": teams,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Export compact team/player/metric gained data for a WOM competition.")
    parser.add_argument("--comp-id", type=int, required=True)
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    result = asyncio.run(fetch_competition(args.comp_id, os.getenv("WOM_API_KEY"), os.getenv("WOM_DISCORD")))

    payload = json.dumps(result, indent=2, ensure_ascii=False)

    if args.stdout:
        print(payload)
    else:
        out_path = args.out or f"comp_{args.comp_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(payload)
        total_players = sum(len(players) for players in result["teams"].values())
        print(
            f"Wrote {len(result['teams'])} teams, {total_players} players → {out_path}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
