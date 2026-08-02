# Changelog

All notable changes to api-backend are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`pyproject.toml` holds the version; `app/version.py` reads it, and both
`GET /version` and the OpenAPI `info` block report it. Never hardcode it
anywhere else. Bump with `uv version --bump patch|minor` (or `alpha|beta|rc` for a
prerelease, `stable` to drop the tag). A MAJOR bump is the maintainer's call
and is never made automatically. The bump happens once, when the accumulated
work is about to be pushed - not per component.

## [1.12.0] - 2026-08-02

### Changed

- `GET /tilerace/events/{event_id}/rolls` returns the event's full roll history
  when `limit` is omitted. The parameter defaulted to 25 and was clamped to 100,
  so the web roll feed could not show older rolls at all. `limit` is now
  optional and only caps the page when a caller passes it (`>= 1`).

### Fixed

- Flipping a background service from the control panel now takes effect in every
  worker. `PUT /config/services/toggles/{service_key}` started or stopped the
  service in whichever worker served the request, so with three gunicorn workers
  a toggle reached one of them and the other two kept running the opposite of
  what the panel showed. The endpoint persists the toggle and publishes on
  `foundry:service_toggles`; `ToggleDispatchService`, running in every worker,
  applies it. The dispatcher is deliberately outside the toggle registry - it
  cannot be used to switch itself off.
- Clan-chat dispatches now reach every connected RuneLite client. Gunicorn runs
  three workers, each with its own in-process connection manager, but
  `POST /ccdispatch` broadcast straight into whichever worker served the
  request - so a message found a given client roughly one time in three. The
  endpoint publishes on `foundry:ccdispatch` instead, and a subscriber in every
  worker delivers to the sockets it holds, which is how the Discord side has
  always worked. A dedicated channel rather than `foundry:discord_chat`, whose
  consumer also runs the spacebar-check accounting.
- `GET`ting a targeted dispatch's 404 is truthful again across workers: which
  connections are attached now lives in Valkey (`WsRegistry`) rather than in one
  worker's memory, scored by a heartbeat so a crashed worker's entries age out
  instead of leaking.
- WebSocket metrics stopped under-reporting. All three workers wrote their own
  `metric_records` row each minute holding only their own share, and the
  `service_status` upsert was last-writer-wins. One worker now takes a Valkey
  lease per interval and writes a single row with cluster-wide counts; dispatch
  tallies go through a shared counter, so they are conserved rather than sampled.

### Changed

- The integration suite runs in 20s instead of 244s. Its truncation fixture used
  to build a fresh engine per test and issue one `TRUNCATE` per table, ~91 round
  trips against 90 tables, and the app rebooted its whole lifespan for every
  test. The table list is now resolved once and truncated in a single statement
  on a session-scoped engine, and the app boots once per worker. It also takes
  its Postgres and Valkey from the test runner when offered
  (`TEST_DATABASE_URL` / `TEST_VALKEY_URI`), cloning a migrated template
  database per pytest-xdist worker rather than running Alembic each time.

## [1.11.0] - 2026-08-02

### Security

- `GET /tilerace/active`, the one unauthenticated tile race route, now returns a
  masked board. Fog of war is enforced on the server: a path cell beyond the
  furthest team is reduced to `{cell_x, cell_y, path_position}` before any tile
  is embedded, so its title, description, requirement and modifiers - traps,
  snakes/ladders targets, sabotage amounts - can no longer be scraped ahead of
  the race. Previously fog was applied only by the browser and the whole
  unrevealed board shipped to any caller. The response also drops the event and
  per-team Discord ids, `discord_permissions`, each team's `pending_effects`,
  and the `signups[]` roster; `teams[].members` is now `{rsn, is_captain}` only.
  A signed-in caller gets `my_signup` and `my_team_id` in place of the roster,
  and everyone gets `signup_count`. Staff keep the full shape on
  `GET /tilerace/events/{id}`.

## [1.10.0] - 2026-08-01

### Fixed

- A tile whose requirement is an "any one of" group no longer reads as several
  outstanding items. The submission context counted unticked leaves, which is
  the wrong question for an `or`: it now sends `outstanding`, the number of
  further submissions actually required, where an `or` costs its cheapest branch
  and a `not` costs nothing. Each leaf carries `needed`, true only while proving
  it would bring the tile closer to satisfied - so every branch of an unproved
  choice is offered, the moment one lands the rest stop being asked for, and a
  leaf under a `not` is never asked for at all. The context also carries
  `requirement_lines`, the tree rendered with its "Any one of:" headings and
  submitted leaves struck through, so the bot prints the shape instead of
  flattening it.

### Changed

- Requirement evaluation moved out of `_requirement_leaves` into
  `_requirement_state`, which owns `is_satisfied`, `outstanding_count` and
  `leaf_catalog`. Key derivation and "what does this team still owe" are
  different questions and the module was over the size limit.

## [1.9.0] - 2026-08-01

### Added

- A `trap` cell modifier. Landing on it rolls the trap's own dice - count and
  faces are fixed when the trap is placed, not taken from the board's roll - and
  walks the team back that many tiles, never past the start. The setback is
  counted from the cell's own `path_position`, so a jump sharing the cell cannot
  shift it. Each team springs a given trap cell once and the sprung positions
  are kept in `pending_effects.traps_sprung`, so a board may carry several traps
  and every one of them still bites. A trap cell carries no `tile_id` and so
  never gates a roll - a team parked on a spent trap rolls on without staff
  review. The team's Discord channel is told what the trap rolled and where it
  landed them, and a trap they have already sprung says so instead.

## [1.8.0] - 2026-08-01

### Added

- A roll publishes a `roll` command on the tile race Discord channel, so the
  rolling team's own channel gets the result and the tile they landed on. The
  requirement tree is rendered to text here rather than in the bot, which holds
  no tile race state: `or` reads as "Any one of", `not` as "Without", and a
  top-level `and` is flattened. Landing effects - snakes and ladders, extra
  rolls, skipped turns, the end pad - are worded for the team as well. Nothing
  is reported back, and a team with no provisioned channel publishes nothing.
  Publishing happens after the commit and swallows its own failures, so a
  Discord outage can never cost a roll that is already recorded.

## [1.7.0] - 2026-08-01

### Added

- Tile race submissions. `tilerace_submissions` records one row per requirement
  leaf a team proves, with its re-hosted screenshots, and drives the board:
  `GET /tilerace/submissions/context`, `POST /tilerace/events/{id}/submissions`
  and `POST .../submissions/threads/{thread_id}/review` are the service-key half
  discord-server calls; `GET .../submissions`, `PATCH .../submissions/{id}` and
  `DELETE .../submissions/{id}` are the staff review queue.
- Requirement leaves get stable content-derived keys (`_requirement_leaves.py`),
  so reordering a tile's items or editing an unrelated branch leaves existing
  submissions pointing at the same leaf. `or` and `not` nodes are evaluated as a
  tree rather than counted.
- `tilerace_events.discord_submissions_channel_id`: the provisioning command and
  its result now carry an event-wide `#submissions` channel every team can see.

### Changed

- A roll is unlocked by a *claim*, not by staff approval. A tile counts as
  claimed once every requirement leaf carries a submission that has not been
  rejected, matching the rules teams were given: roll as soon as you claim, and
  get rolled back if the proof does not hold up.
- `tilerace_tile_completions` carries a `status` (`claimed` / `approved` /
  `rejected`), so the board has one state source. Existing staff-set rows are
  `approved`.
- Rejecting or deleting a submission sends the team back to the tile it was
  proving and stores where it had reached in `tilerace_teams.furthest_position`;
  claiming that tile again hands the position back.

## [1.6.0] - 2026-08-01

### Added

- Staff can switch which of a member's linked RSNs a tile race entry races
  under, after the teams are drawn. `PATCH /tilerace/events/{id}/roster/{user}`
  takes `account_id`, moving the RSN and its ranking score without touching the
  team assignment or the captain badge, and `GET .../roster/{user}/accounts`
  lists the member's linked RSNs for the picker. A raw `rsn` still works for
  staff-added members with no linked account and now drops the stale account
  link rather than leaving it pointing at a different name.
- Elevated Discord permissions for tile race teams inside their own managed
  channels, event-wide, via `PATCH /tilerace/events/{id}/discord/permissions`:
  `pin_messages`, `manage_messages`, `mention_everyone`, `manage_threads`,
  `manage_channel` and `voice_moderation`. Stored on
  `tilerace_events.discord_permissions` (migration `0062`), reported by the
  event payload, and carried in every provisioning command so a change is
  applied to the channels that already exist - never a teardown. Each toggle
  only grants; switching one off returns the flag to inherited rather than
  denying it.

### Fixed

- The tile race Discord contract tests read the monorepo-root `fixtures/` at
  import time, which raised `FileNotFoundError` during collection in this
  repository's own CI, where only this submodule is checked out. The run aborted
  before any of the 606 selected tests executed, and had done so on every push
  since `0061` landed. Both files now carry the same guard the other
  shared-fixture suites use - `skipif` on the fixtures directory, with the read
  inside a helper, since a module-level read happens before `pytestmark` can
  skip anything.

## [1.5.1] - 2026-08-01

### Security

- cryptography 46.0.7 -> 50.0.0, starlette 1.0.1 -> 1.3.1, python-multipart
  0.0.27 -> 0.0.32, pydantic-settings 2.13.1 -> 2.14.2, pyasn1 0.6.3 -> 0.6.4
  and idna 3.11 -> 3.18, clearing all 13 Dependabot advisories. Lockfile only -
  no declared constraint moved. The cryptography advisory needs 48.0.1, so
  staying on 46.x was not an option; `python-jose[cryptography] 3.5.0` declares
  `cryptography>=3.4.0` with no ceiling and fastapi 0.138.0 declares
  `starlette>=0.46.0` with no ceiling, so neither jump required a parent bump.

### Fixed

- The member snapshot integration fixture sets `users.updated_at`. The column
  is `nullable=False` with no server default, so seeding a `User` without it
  failed on a not-null violation before the endpoint was ever reached. The
  roster fixtures were corrected in 1.4.0; this one was missed.

## [1.5.0] - 2026-07-31

### Added

- Tile race rolling can be paused. `rolls_paused` on the event blocks every
  team's roll with a 409 without ending the game, so a board can be fixed or a
  dispute settled without resorting to finishing the event. It is checked after
  the game-over gate, so a finished event still reports "Game over".
- Tile race Discord provisioning: `POST .../discord/setup`, `.../discord/sync`
  and `.../discord/teardown` publish a command on `foundry:tilerace_discord`
  for discord-server to act on, and `POST .../discord/result` is the
  service-key callback it reports the created (or cleared) ids back through.
  The command always carries the full desired shape rather than a diff, so an
  extra sync is harmless. Role, channel and category ids are stored on the
  event and team rows; the seam is pinned by `fixtures/tilerace_discord.json`.
- Anything that changes a roster or a team name now pushes to Discord when the
  event is provisioned - team rename, roster add, move, captain change, remove,
  team generation and reset. Without it a member dropped from a roster on the
  site kept the role and the channel access that came with it. Deleting a team
  emits a targeted `teardown_team` so its role and channels go with it instead
  of lingering in the guild with nothing pointing at them.

### Changed

- `_helpers.py` is split: the pure serializers move to `_serializers.py`,
  leaving the session-bound helpers behind. Both files were over the size limit
  with the new fields added.

## [1.4.0] - 2026-07-31

### Changed

- Tile race team generation now balances score mass instead of draft position.
  Ranking points are heavily right-skewed, and the snake order only compensated
  the team holding the top player with the worst pick of the next round, which
  left team averages decaying monotonically from first team to last - 302,440
  against 156,039 on a real 17-team draft. Each pick now lands on whichever
  open team has the lowest average, cutting the worst-to-best spread from 2.12x
  to 1.39x on a comparably skewed pool.
- `team_size` remains a hard maximum, but the remainder is spread one member at
  a time across the leading teams rather than dumped into a final runt team.
  Thirteen signups at size four now yield `[4, 3, 3, 3]`, not `[4, 4, 4, 1]`,
  so no team's average rests on a single member.

### Fixed

- The tile race roster integration fixtures seeded a `User` without
  `updated_at` and read an event id after the commit that expired it, failing
  with `NotNullViolationError` and `MissingGreenlet` before reaching any
  assertion.

## [1.3.0] - 2026-07-31

### Added

- Tile race team generation: `POST /tilerace/events/{id}/teams/generate` takes
  `{team_size, balance_raids_kc, raids_kc_threshold}` and builds the teams from
  the signup pool, so teams no longer have to be created by hand first.
  `team_size` is a hard maximum - `ceil(n / size)` teams, the last one taking
  the remainder - and existing teams keep their name, colour and icon.
  `balance_raids_kc` swaps members between teams until every team holds someone
  whose highest CoX/ToB/ToA kill count meets the threshold, where the supply of
  raiders allows.
- `POST /tilerace/events/{id}/teams/reset` returns an event to bare signups by
  unassigning every member, and staff roster management arrives alongside it:
  `GET /tilerace/events/{id}/roster/candidates`, `POST .../roster`,
  `PATCH .../roster/{discord_user_id}` (move team, set captain, correct RSN) and
  `DELETE .../roster/{discord_user_id}`. Staff can place a member who never
  signed up, which is how replacements get added.
- A tile race team holds at most one captain, enforced by a partial unique index
  on `tilerace_signups (team_id) WHERE is_captain`. Appointing a captain via
  `PATCH .../roster/{discord_user_id}` demotes whoever held it, moving a captain
  to another team drops the badge unless the same request re-appoints them, and
  a losing race returns 409 rather than a 500. Any member of a team can be
  appointed - the signup-time `wants_captain` flag only seeds the first pick
  during generation.
- Team and signup payloads carry `raids_kc` (highest single-raid KC from
  `player_snapshots`); signups also carry `team_id`, `is_captain` and
  `added_by_staff`, and events carry `team_size`.
- `GET /members/me/snapshot` returns `ehp` and `ehb`, and its `skills` map now
  carries `overall`. Migration `0059` adds the two columns to
  `player_snapshots`; the ranking service reads the values WOM already computes
  per account type off the bulk-hiscores `player` object. The ranking input
  stays filtered to the configured skills, so scoring is unchanged.

### Changed

- Tile race rosters now live on `tilerace_signups` (`team_id` FK with
  `ON DELETE SET NULL`, plus `is_captain` and `added_by_staff`); migration `0060`
  backfills rows from the `tilerace_teams.members` JSONB and drops that column.
  Team rosters are derived from signups at serialize time, so team operations
  are reversible: deleting a team returns its members to the unassigned pool
  instead of destroying them.

### Removed

- `POST /tilerace/events/{id}/teams/scramble`, replaced by `.../teams/generate`.
  Scramble deleted every signup row after assigning teams, which made the
  transition to teams a one-way door - there was no way back to bare signups and
  no way to inspect or adjust the pool afterwards.

## [1.2.0] - 2026-07-29

### Added

- Saved and queued tracks carry cover art. `TrackIn` gains `artwork`, migration
  `0058` adds the column, and it travels on the `add` command as well. The art
  could not be recovered later: a saved track re-resolves its audio at play time
  and lands on a mirror whose own cover is not the one the user picked.
- `ActivityOut.actor_name`, stamped by discord-utils, for the same reason
  `SessionTrack.requester_name` is.
- `SessionTrack.requester_name`, stamped by discord-utils. This service cannot
  produce it - the `users` table only knows people who have logged into the
  website, and nothing here can see a per-server nickname - so the name crosses
  the seam with the track or not at all.
- `GET /music/sessions/{id}/history`: what a session has already played, newest
  first. The Discord panel shows the last ten because that is what fits in two
  rows of buttons; the website is given the whole list the bot still keeps, and
  each entry carries the track metadata rather than a rendered line so it can be
  queued again or saved to a playlist.
- Clan listening stats. `MusicStatsService` consumes the `music:events` Valkey
  stream through a consumer group and writes `music_counters` and
  `music_track_plays` - the two tables migration `0057` created and nothing
  filled until now. A stream rather than pubsub so playback never blocks on a
  database write and a restart loses nothing that happened while it was down.
- `GET /music/stats` and `GET /music/stats/top-tracks`: minutes listened, tracks
  played, skips, sessions, the source split and the most-played recordings.
  Nothing is per member and nothing can be - the rows carry a guild and a track
  and never a user id, so there is no filter to forget.
- Top tracks are keyed on the ISRC where the source gave one and on a digest of
  the normalised metadata where it did not. Keying on the source identifier
  would list the same song once per source.
- `music_stats` joins the service toggles, so the consumer can be stopped
  without stopping the API.

### Changed

- Every message is claimed with `SET NX` before it is counted and the claim is
  released if the transaction fails. Stream delivery is at least once, so a
  redelivery after a crash would otherwise inflate a total that nothing can
  audit back down.
- `_live_schemas.py` now holds only what is read; the command bodies moved to
  `_command_schemas.py`.
- The playlist import route no longer describes Spotify as a source. Spotify
  playlist, album and artist links cannot be imported at all, so offering them
  advertised an import that always fails.

## [1.1.0] - 2026-07-28

### Added

- Music playlists (`/music/playlists`): list, read, create, rename, publish,
  delete, and replace or append tracks. A playlist is private to its owner
  unless marked public; a public one is readable and loadable by anyone but
  editable only by its owner.
- Playlist tracks store the ISRC alongside the source identifier, so a track
  whose source id dies can be re-resolved instead of vanishing.
- A read-only service-key surface at `/music/bot/{discord_user_id}/playlists`
  for discord-utils, which holds no user JWT. It names the user it acts for and
  gets exactly that user's visibility. It cannot write.
- Migration `0057`: `playlists`, `playlist_tracks`, `music_counters` and
  `music_track_plays`. The two counter tables are populated in a later stage;
  no user id is stored against playback.
- `fixtures/music_playlist.json` pins the playlist payload discord-utils parses
  with its own models. Both sides assert against it, so a renamed field fails a
  test instead of a bot.
- A live session surface at `/music/sessions`: the sessions playing right now,
  their queue, their activity feed, and whether the caller may drive them. It
  reads the ephemeral Valkey keys discord-utils writes, so it needs neither a
  database nor a Discord gateway and can never disagree with the Discord panel.
- `POST /music/sessions/{id}/commands` publishes a control onto `music:commands`
  for whichever process owns the player. api-backend holds no voice connection,
  so a web control can do nothing a panel button could not. Authority is checked
  here and again in discord-utils.
- `GET /music/live`, a WebSocket carrying session state as it changes, fed by a
  `music:state` subscriber that mirrors the existing chat subscriber. It
  authenticates with its first frame rather than a header or a query string: a
  browser cannot set headers on a socket, and a token in a URL lands in access
  logs.
- `fixtures/music_bridge.json` pins the whole web-to-Discord seam - the session
  hash, the command envelope and the state notice - asserted from both sides.
- `GET /music/search`, resolving a query or a link into tracks through
  Lavalink's REST API. It needs no session, no voice channel and no bot: a
  search is a lookup, not playback, which is what lets a playlist be built when
  nothing is playing. A link is loaded as itself, and a link to a playlist comes
  back as all of its tracks. `LAVALINK_URI` and `LAVALINK_PASSWORD` are new here
  and are used for search only; with either missing, search answers 503 rather
  than failing when pressed.
- The session's starting volume, loop and shuffle are read from the hash the bot
  writes. They used to be absent until someone changed them, and a missing
  volume read as 0%.
- Shuffle is reported on the session payload and set through the command
  surface as an explicit on/off rather than a toggle, so two people pressing at
  once cannot invert each other. Same reasoning as pause and resume.
- `POST /music/playlists/import`, saving a YouTube, YouTube Music or Spotify
  playlist link as a new playlist. It takes the source's own name unless one is
  given, and imports up to the 500 a playlist may hold rather than the 25 a
  search shows. Only metadata is stored, so a Spotify import keeps its ISRC and
  resolves to playable audio at play time.
- Load failures now report the reason rather than lavaplayer's generic "Something
  went wrong while looking up the track", which is all Lavalink puts in its
  top-level message - the specific cause sits further down the stack trace, and
  the deepest one is the specific one. Where that cause is a platform
  restriction rather than a mistake, the message says what it means and what
  will work instead: Spotify only serves playlists, albums and artist pages to a
  signed-in account, so those links cannot be imported with app credentials
  (single tracks still resolve), and it serves the playlists it generates itself
  to nobody at all.
- An `add` command carrying the tracks the caller picked. The metadata travels
  with the command rather than being searched again by the bot, which could
  otherwise queue a different result than the one chosen.
- Every Discord id in a web-facing music payload is a string: the voice channel,
  the guild, a track's requester, an activity actor and a playlist's owner. A
  snowflake is 64-bit and a JSON number is an IEEE double in a browser, so ids
  above 2^53 arrive with their last digits rounded - which addresses a channel
  nobody is in and makes every playlist look like someone else's.

## [1.0.0] - 2026-07-28

First versioned release. The service has been in production; this establishes
1.0.0 as the baseline rather than describing everything built before it.

### Added

- `GET /version`, reporting the package version plus the commit and build
  timestamp baked into the container image as build arguments.
- `GET /health` moved under the new `meta` tag; the path is unchanged.
- OpenAPI `info.description`, per-tag sidebar descriptions, `x-tagGroups`
  sections, and declared production and local servers.
- Declared security schemes: `DiscordJWT` (bearer), `MemberApiKey` and
  `MetricsApiKey` (both the `verification-code` header). The API reference can
  now authenticate and issue live requests.
- Reusable error responses in `app/docs/responses.py`, attached per router, so
  401, 403, 404, 502 and 503 appear in the reference instead of only 200.
- A docstring on every one of the 279 documented operations.
- Branding on the Scalar reference page: clan palette, favicon, dark default,
  and persisted auth between reloads.

### Changed

- Missing credentials now return `401` instead of FastAPI's `422`. Previously
  the credential was an ordinary required header, so its absence was reported
  as a validation error. Invalid and revoked credentials returned `401` before
  and still do.
- `/reference` operations no longer carry a duplicated `reference` tag.
