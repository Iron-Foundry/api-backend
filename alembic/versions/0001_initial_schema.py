"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import BIGINT, JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE users (
            discord_user_id          BIGINT      PRIMARY KEY,
            discord_username         TEXT        NOT NULL,
            guild_id                 BIGINT      NOT NULL DEFAULT 0,
            rsn                      TEXT        UNIQUE,
            clan_rank                TEXT,
            discord_roles            TEXT[]      NOT NULL DEFAULT '{}',
            ticket_ids               INT[]       NOT NULL DEFAULT '{}',
            total_loot_value         BIGINT      NOT NULL DEFAULT 0,
            clan_donated             BIGINT      NOT NULL DEFAULT 0,
            collection_log_slots     INT         NOT NULL DEFAULT 0,
            collection_log_slots_max INT         NOT NULL DEFAULT 0,
            stats_opt_out            BOOLEAN     NOT NULL DEFAULT FALSE,
            api_key                  TEXT        UNIQUE,
            key_is_active            BOOLEAN     NOT NULL DEFAULT FALSE,
            key_created_at           TIMESTAMPTZ,
            key_expires_at           TIMESTAMPTZ,
            temp_vc_lock_status      TEXT,
            temp_vc_member_limit     INT,
            temp_vc_bitrate          INT,
            created_at               TIMESTAMPTZ NOT NULL,
            updated_at               TIMESTAMPTZ NOT NULL,
            CONSTRAINT users_rsn_unique UNIQUE NULLS NOT DISTINCT (rsn)
        )
    """)
    op.execute("CREATE INDEX users_rsn_lower ON users (LOWER(rsn)) WHERE rsn IS NOT NULL")
    op.execute("CREATE INDEX users_guild ON users (guild_id, discord_user_id)")

    # ── events ─────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE events (
            id              BIGSERIAL   PRIMARY KEY,
            type            TEXT        NOT NULL,
            timestamp       TIMESTAMPTZ NOT NULL,
            player_name     TEXT,
            sender          TEXT,
            is_league_world BOOLEAN     NOT NULL DEFAULT FALSE,
            raw_message     TEXT,
            data            JSONB       NOT NULL DEFAULT '{}'
        )
    """)
    op.execute("CREATE INDEX events_player_type ON events (player_name, type)")
    op.execute("CREATE INDEX events_time ON events (timestamp DESC)")
    op.execute("CREATE INDEX events_type ON events (type)")

    # ── coffer_events ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE coffer_events (
            id              BIGSERIAL   PRIMARY KEY,
            timestamp       TIMESTAMPTZ NOT NULL,
            player_name     TEXT        NOT NULL,
            sender          TEXT,
            is_league_world BOOLEAN     NOT NULL DEFAULT FALSE,
            raw_message     TEXT,
            amount          BIGINT      NOT NULL,
            is_donation     BOOLEAN     NOT NULL
        )
    """)
    op.execute("CREATE INDEX coffer_events_player ON coffer_events (player_name)")
    op.execute("CREATE INDEX coffer_events_time ON coffer_events (timestamp DESC)")

    # ── membership_events ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE membership_events (
            id              BIGSERIAL   PRIMARY KEY,
            timestamp       TIMESTAMPTZ NOT NULL,
            player_name     TEXT        NOT NULL,
            sender          TEXT,
            is_league_world BOOLEAN     NOT NULL DEFAULT FALSE,
            raw_message     TEXT,
            expelled_by     TEXT
        )
    """)
    op.execute("CREATE INDEX membership_events_player ON membership_events (player_name)")
    op.execute("CREATE INDEX membership_events_time ON membership_events (timestamp DESC)")

    # ── leaderboards ───────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE leaderboards (
            player_name  TEXT NOT NULL,
            activity     TEXT NOT NULL,
            variant      TEXT NOT NULL DEFAULT '',
            time_seconds INT  NOT NULL,
            PRIMARY KEY (player_name, activity, variant)
        )
    """)
    op.execute("CREATE INDEX leaderboards_activity ON leaderboards (activity, time_seconds)")

    # ── metrics ────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE metrics (
            id           TEXT        PRIMARY KEY,
            count        INT,
            total_value  BIGINT,
            achieved_at  TIMESTAMPTZ,
            last_updated TIMESTAMPTZ
        )
    """)

    # ── tickets ────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE tickets (
            ticket_id               SERIAL      PRIMARY KEY,
            guild_id                BIGINT      NOT NULL,
            ticket_type             TEXT        NOT NULL,
            status                  TEXT        NOT NULL DEFAULT 'open',
            created_at              TIMESTAMPTZ NOT NULL,
            closed_at               TIMESTAMPTZ,
            last_message_at         TIMESTAMPTZ,
            channel_id              BIGINT,
            creator_id              BIGINT      NOT NULL,
            creator_name            TEXT        NOT NULL,
            assigned_staff          BIGINT[]    NOT NULL DEFAULT '{}',
            participants            BIGINT[]    NOT NULL DEFAULT '{}',
            closed_by_id            BIGINT,
            first_staff_response_at TIMESTAMPTZ,
            panel_message_id        BIGINT,
            staff_note              TEXT,
            close_reason            TEXT,
            reopen_history          JSONB       NOT NULL DEFAULT '[]'
        )
    """)
    op.execute("CREATE INDEX tickets_guild_status ON tickets (guild_id, status)")
    op.execute("CREATE INDEX tickets_creator ON tickets (guild_id, creator_id)")
    op.execute("CREATE INDEX tickets_channel ON tickets (channel_id)")
    op.execute("CREATE INDEX tickets_type ON tickets (ticket_type)")

    # ── transcripts ────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE transcripts (
            ticket_id INT PRIMARY KEY REFERENCES tickets(ticket_id) ON DELETE CASCADE,
            entries   JSONB NOT NULL DEFAULT '[]'
        )
    """)

    # ── survey_templates ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE survey_templates (
            template_id TEXT        PRIMARY KEY,
            title       TEXT        NOT NULL,
            questions   JSONB       NOT NULL DEFAULT '[]',
            created_at  TIMESTAMPTZ
        )
    """)

    # ── survey_active ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE survey_active (
            id          INT  PRIMARY KEY DEFAULT 1,
            template_id TEXT NOT NULL REFERENCES survey_templates(template_id),
            ticket_id   INT  REFERENCES tickets(ticket_id),
            started_at  TIMESTAMPTZ
        )
    """)

    # ── survey_responses ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE survey_responses (
            ticket_id    INT  PRIMARY KEY REFERENCES tickets(ticket_id) ON DELETE CASCADE,
            template_id  TEXT NOT NULL REFERENCES survey_templates(template_id),
            responses    JSONB NOT NULL DEFAULT '{}',
            submitted_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX survey_responses_template ON survey_responses (template_id)")

    # ── config ─────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE config (
            guild_id BIGINT NOT NULL,
            key      TEXT   NOT NULL,
            value    JSONB  NOT NULL DEFAULT '{}',
            PRIMARY KEY (guild_id, key)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS config")
    op.execute("DROP TABLE IF EXISTS survey_responses")
    op.execute("DROP TABLE IF EXISTS survey_active")
    op.execute("DROP TABLE IF EXISTS survey_templates")
    op.execute("DROP TABLE IF EXISTS transcripts")
    op.execute("DROP TABLE IF EXISTS tickets")
    op.execute("DROP TABLE IF EXISTS metrics")
    op.execute("DROP TABLE IF EXISTS leaderboards")
    op.execute("DROP TABLE IF EXISTS membership_events")
    op.execute("DROP TABLE IF EXISTS coffer_events")
    op.execute("DROP TABLE IF EXISTS events")
    op.execute("DROP TABLE IF EXISTS users")
