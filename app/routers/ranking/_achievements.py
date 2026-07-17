from __future__ import annotations

from app.db.models import Event

ACHIEVEMENT_TYPES = {
    "quest",
    "diary",
    "combat_achievement",
    "pet",
    "personal_best",
    "collection_log",
    "xp_milestone",
    "level",
    "clue_item",
    "league_relic",
    "league_area",
}


def build_achievement(row: Event) -> dict | None:
    d = row.data or {}
    t = row.type
    if t == "level":
        skill = d.get("skill", "")
        label = "Total Level" if skill == "total" else skill
        return {"type": t, "label": label, "detail": None, "timestamp": row.timestamp}
    if t == "xp_milestone":
        return {
            "type": t,
            "label": d.get("skill", ""),
            "detail": None,
            "timestamp": row.timestamp,
        }
    if t in ("quest", "diary", "combat_achievement"):
        return {
            "type": d.get("achievement_type", t),
            "label": d.get("name", ""),
            "detail": None,
            "timestamp": row.timestamp,
        }
    if t == "pet":
        return {
            "type": t,
            "label": "Pet drop!",
            "detail": None,
            "timestamp": row.timestamp,
        }
    if t == "collection_log":
        return {
            "type": t,
            "label": d.get("item_name", ""),
            "detail": f"Slot {d.get('log_slots')}/{d.get('log_slots_max')}",
            "timestamp": row.timestamp,
        }
    if t == "clue_item":
        return {
            "type": t,
            "label": d.get("item_name", ""),
            "detail": "Clue scroll",
            "timestamp": row.timestamp,
        }
    if t == "personal_best":
        return {
            "type": t,
            "label": d.get("activity", ""),
            "detail": d.get("variant"),
            "timestamp": row.timestamp,
        }
    if t == "league_relic":
        return {
            "type": t,
            "label": f"Tier {d.get('tier')} League relic",
            "detail": None,
            "timestamp": row.timestamp,
        }
    if t == "league_area":
        area = d.get("area_count")
        label = "Final League area" if area is None else f"League area {area}"
        return {"type": t, "label": label, "detail": None, "timestamp": row.timestamp}
    return None
