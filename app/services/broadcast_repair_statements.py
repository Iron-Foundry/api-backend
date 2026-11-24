"""The SQL statements of the event repair, as data only.

`app/services/broadcast_repair_writes.py` and the two repair scripts read them.
"""

from __future__ import annotations

from sqlalchemy import text

TAG_PATTERN = r"<(int_|str_|switch,|lt>|gt>|at>)"

FETCH_TAGGED = text(
    "SELECT id, type, player_name, sender, raw_message, data, timestamp"
    " FROM events WHERE raw_message ~ :tag ORDER BY id"
)
FIND_DUPLICATE = text(
    "SELECT 1 FROM events WHERE id <> :id AND player_name = :player"
    " AND raw_message = :raw AND _minute_bucket(timestamp) = _minute_bucket(:ts)"
)
DELETE_EVENT = text("DELETE FROM events WHERE id = :id")
UPDATE_EVENT = text(
    "UPDATE events SET type = :type, player_name = :player, raw_message = :raw,"
    " data = :data, user_id = NULL, user_account_id = NULL WHERE id = :id"
)
ADD_LOOT_VALUE = text(
    "UPDATE users SET total_loot_value = total_loot_value + :value,"
    " updated_at = now() WHERE lower(rsn) = lower(:player)"
)
RAISE_CLOG_SLOTS = text(
    "UPDATE users SET collection_log_slots = :slots,"
    " collection_log_slots_max = :max, updated_at = now()"
    " WHERE lower(rsn) = lower(:player) AND collection_log_slots < :slots"
)
COUNT_CLOG = text(
    "INSERT INTO metrics (id, count, last_updated) VALUES ('total_clogs', 1, now())"
    " ON CONFLICT (id) DO UPDATE SET count = metrics.count + 1, last_updated = now()"
)
UPSERT_PERSONAL_BEST = text(
    "INSERT INTO leaderboards (player_name, activity, variant, time_seconds)"
    " VALUES (:player, :activity, :variant, CAST(:time AS numeric(10,3)))"
    " ON CONFLICT (player_name, activity, variant) DO UPDATE"
    " SET time_seconds = least(leaderboards.time_seconds, EXCLUDED.time_seconds)"
)
COUNT_TAGGED_LEADERBOARD = text(
    "SELECT count(*) FROM leaderboards WHERE player_name ~ :tag"
)
DELETE_TAGGED_LEADERBOARD = text("DELETE FROM leaderboards WHERE player_name ~ :tag")
LINK_EVENT_USERS = (
    text(
        "UPDATE events e SET user_id = u.discord_user_id FROM (SELECT"
        " discord_user_id, lower(rsn) AS rsn_lower FROM user_accounts UNION SELECT"
        " discord_user_id, lower(rsn) FROM users WHERE rsn IS NOT NULL) u WHERE"
        " replace(lower(e.player_name), chr(160), ' ') = u.rsn_lower"
        " AND e.user_id IS NULL"
    ),
    text(
        "UPDATE events e SET user_account_id = ua.id FROM user_accounts ua WHERE"
        " replace(lower(e.player_name), chr(160), ' ') = lower(ua.rsn)"
        " AND e.user_account_id IS NULL"
    ),
)
