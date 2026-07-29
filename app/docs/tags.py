"""Sidebar metadata: one description per tag, and the groups tags sit under.

Tag order here is the order Scalar renders sections in. TAG_GROUPS is emitted as
the `x-tagGroups` OpenAPI extension, which Scalar reads to fold the tag list into
collapsible top-level sections.
"""

from typing import Any

TAGS_METADATA: list[dict[str, Any]] = [
    {
        "name": "meta",
        "description": (
            "Liveness and build provenance. `/health` is what the container "
            "healthcheck polls; `/version` reports the package version plus the "
            "commit and timestamp baked into the image."
        ),
    },
    {
        "name": "auth",
        "description": (
            "Discord OAuth2 login and session issuance. `/login` and `/callback` "
            "are browser redirects, not JSON endpoints - open them in a window "
            "rather than calling them from the client below."
        ),
    },
    {
        "name": "members",
        "description": (
            "The signed-in member's own record: linked RuneScape accounts and "
            "which is primary, personal API key, goals, stats snapshots, activity "
            "feed, privacy flags, and their ticket transcripts. Everything under "
            "`/members/me` is scoped to the caller's JWT."
        ),
    },
    {
        "name": "badges",
        "description": (
            "Cosmetic achievement badges: the catalog, who holds each one, and "
            "staff assignment or revocation."
        ),
    },
    {
        "name": "parties",
        "description": (
            "Player-organised group finder. Members create a party, others join "
            "or leave, and each party carries a chat log. Parties expire "
            "automatically via a background task."
        ),
    },
    {
        "name": "music",
        "description": (
            "Saved playlists for the Discord music bots. A playlist is private "
            "to its owner unless it is marked public, and a public one can be "
            "browsed and loaded by anyone but changed only by its owner. Live "
            "playback state is not here: it is ephemeral and never persisted."
        ),
    },
    {
        "name": "feedback",
        "description": (
            "Member-submitted suggestions and reports, with threaded replies, "
            "reactions, pinning, status transitions, and image attachments."
        ),
    },
    {
        "name": "content",
        "description": (
            "The CMS behind the public site's guides and articles. Entries live "
            "in a per-`page_type` category tree, keep a full version history, and "
            "support soft delete, restore, and revert to an earlier version."
        ),
    },
    {
        "name": "surveys",
        "description": (
            "Survey and clan-application templates, their open/visibility state, "
            "and the collected responses."
        ),
    },
    {
        "name": "staff",
        "description": (
            "Staff-only administration: the member roster, RSN corrections and "
            "their cascade across linked records, referral reporting, and ticket "
            "transcripts. Requires a staff role."
        ),
    },
    {
        "name": "role-panels",
        "description": (
            "Self-assign role panels the Discord bot renders as interactive messages."
        ),
    },
    {
        "name": "ticket-config",
        "description": (
            "Ticket type definitions, their panel layout, and the images attached "
            "to each type. Consumed by the Discord bot's ticket system."
        ),
    },
    {
        "name": "clan",
        "description": (
            "Clan-wide competition and statistics surface, sourced from "
            "WiseOldMan. Covers competitions and their recurring schedules, "
            "leaderboards for clues, collection log and kill counts, personal "
            "bests, recent achievements, name changes, and bulk gains batches. "
            "Also carries the clan-chat bridge (`/ccingest`, `/ccdispatch`)."
        ),
    },
    {
        "name": "ranking",
        "description": (
            "The clan's internal rank engine: per-player rank results with a "
            "point breakdown, run status, and staff-triggered preview or full "
            "recalculation."
        ),
    },
    {
        "name": "frenzy",
        "description": (
            "Frenzy events - team-based scoring competitions built from reusable "
            "templates. Covers event lifecycle, teams, submission review, point "
            "calculation, WiseOldMan sync, and leaderboards."
        ),
    },
    {
        "name": "tilerace",
        "description": (
            "Tile race events: the shared tile repository, event lifecycle, "
            "signups, team assignment and scrambling, dice rolls, sabotages, "
            "fog of war, and completions."
        ),
    },
    {
        "name": "osrs-cache",
        "description": (
            "Read-only proxy to the internal cache service, which decodes the "
            "live OSRS game cache. Items and their variants, NPCs, objects, "
            "sprites, rendered item icons, and slippy-map data. No auth; "
            "responses are immutable per cache build."
        ),
    },
    {
        "name": "reference",
        "description": (
            "Static game reference data refreshed on a schedule: loot tables "
            "parsed from the OSRS Wiki (forward by source, reverse by item) and "
            "EHP/EHB efficiency rates from WiseOldMan. No auth."
        ),
    },
    {
        "name": "discord",
        "description": (
            "Read-through lookups of the Discord guild - channels, roles, "
            "emojis, members - so the web control panel can populate pickers "
            "without its own bot token."
        ),
    },
    {
        "name": "runelite-configs",
        "description": (
            "Shared RuneLite plugin configuration profiles the clan distributes "
            "to its members."
        ),
    },
    {
        "name": "ironclad",
        "description": (
            "Ingest seam for the Ironclad RuneLite plugin. Sanitizes death "
            "payloads before they reach the clan's death log."
        ),
    },
    {
        "name": "config",
        "description": (
            "Runtime configuration the control panel edits without a redeploy: "
            "rank mappings, Discord role bindings, per-page permissions, feature "
            "toggles for the Discord services, ballot tokens, and panel layout."
        ),
    },
    {
        "name": "metrics",
        "description": (
            "Operational telemetry: per-endpoint request history, bandwidth, "
            "outbound WiseOldMan rate-limit headroom, and the health and uptime "
            "of every service in the stack. Reporting endpoints take the shared "
            "service key."
        ),
    },
    {
        "name": "assets",
        "description": (
            "Uploaded image and file storage. `GET /assets/file/{filename}` "
            "serves an asset and can downscale rasters to a cached thumbnail via "
            "`?w=`; responses are immutably cached."
        ),
    },
]

TAG_GROUPS: list[dict[str, Any]] = [
    {"name": "Platform", "tags": ["meta", "auth", "config", "metrics", "assets"]},
    {
        "name": "Members and Community",
        "tags": [
            "members",
            "badges",
            "parties",
            "music",
            "feedback",
            "content",
            "surveys",
            "staff",
            "role-panels",
            "ticket-config",
        ],
    },
    {
        "name": "Competitions and Events",
        "tags": ["clan", "ranking", "frenzy", "tilerace"],
    },
    {
        "name": "Game Data and Integrations",
        "tags": ["osrs-cache", "reference", "discord", "runelite-configs", "ironclad"],
    },
]
