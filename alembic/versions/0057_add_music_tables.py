"""add music playlists and play counters

Revision ID: 0057
Revises: 0056
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playlists",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_discord_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_discord_id", "name", name="uq_playlist_owner_name"),
    )
    op.create_index("ix_playlists_public", "playlists", ["is_public"])

    op.create_table(
        "playlist_tracks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("playlist_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("isrc", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["playlist_id"], ["playlists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "playlist_id", "position", name="uq_playlist_track_position"
        ),
    )

    op.create_table(
        "music_counters",
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "ms_listened", sa.BigInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "tracks_played", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("skips", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "sessions", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("guild_id", "day"),
    )

    op.create_table(
        "music_track_plays",
        sa.Column("track_key", sa.Text(), nullable=False),
        sa.Column(
            "has_isrc", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column(
            "play_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "skip_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("last_played_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("track_key"),
    )
    op.create_index("ix_music_track_plays_count", "music_track_plays", ["play_count"])


def downgrade() -> None:
    op.drop_index("ix_music_track_plays_count", table_name="music_track_plays")
    op.drop_table("music_track_plays")
    op.drop_table("music_counters")
    op.drop_table("playlist_tracks")
    op.drop_index("ix_playlists_public", table_name="playlists")
    op.drop_table("playlists")
