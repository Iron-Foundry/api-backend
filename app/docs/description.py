"""Markdown introduction rendered at the top of the API reference."""

DESCRIPTION = """
The backend for **The Iron Foundry**, an Old School RuneScape clan. It serves the
community site at [ironfoundry.cc](https://ironfoundry.cc), the clan's Discord
bots, and the in-game RuneLite plugin from one PostgreSQL + Valkey stack.

## Authentication

Three credentials exist, each for a different caller.

**`DiscordJWT`** - the browser session. `GET /auth/login` redirects to Discord
OAuth2; `GET /auth/callback` verifies guild membership, upserts the user, and
redirects back to the frontend with an HS256 JWT in the query string. Send it as
`Authorization: Bearer <token>` on every member or staff endpoint. `GET /auth/me`
returns the decoded profile with Discord roles, refreshed when stale.

**`MemberApiKey`** - the RuneLite plugin. Each member holds a personal key from
`GET /members/me/api-key` (rotate with `POST /members/me/api-key/rotate`), sent as
a `verification-code` header. `POST /auth/token` trades the same key for a JWT
when a plugin needs member-scoped web endpoints. Revoked keys are rejected.

**`MetricsApiKey`** - service-to-service. A shared secret the Discord services
present, also as `verification-code`, to report telemetry and dispatch clan chat.

Missing or invalid credentials return `401`. A valid token whose roles do not
satisfy an endpoint's permission returns `403`.

## Conventions

Timestamps are UTC ISO-8601. Request and response bodies are JSON unless an
endpoint serves a binary asset. Collections large enough to page take `limit` and
`offset` query parameters; the rest return the full set. Validation failures
return `422` with FastAPI's error array, naming the offending field in `loc`.

## Realtime

`WS /ccdispatch` is the clan-chat bridge: the RuneLite plugin connects with its
`verification-code` header and receives messages relayed from Discord over Valkey
pubsub, while `POST /ccingest` carries in-game chat the other way. Party chat
polls over plain HTTP instead.

## Related services

`/osrs-cache/*` proxies an internal service that decodes the live OSRS game cache
into items, NPCs, objects, sprites, rendered item icons, and map tiles.
`/reference/*` serves loot tables scraped from the OSRS Wiki and EHP/EHB
efficiency rates from WiseOldMan. Both refresh on a schedule; neither needs
authentication.
""".strip()
