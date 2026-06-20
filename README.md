# Iron Foundry - API Backend

REST API backend for the Iron Foundry platform. Built with FastAPI and served by Gunicorn.

---

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (package manager)

---

## Setup

```bash
uv sync
```

## Run (development)

```bash
uv run uvicorn app.main:app --reload
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `MONGO_URI` | Yes | `mongodb://localhost:27017` | MongoDB connection URI |
| `MONGO_DB` | No | `foundry` | MongoDB database name |
| `VALKEY_URI` | Yes | `redis://localhost:6379` | Valkey/Redis connection URI |
| `WOM_GROUP_ID` | No | - | Wise Old Man group ID - enables RSN name change tracking when set |
| `WOM_GROUP_KEY` | No | - | WOM group token (private groups only) |
| `WOM_CLAN_NAME` | No | `Iron Foundry` | Must match `clan_name` in stat collections |

---

## Structure

```
app/
  main.py          - FastAPI application entry point, background services
  dependencies.py  - Shared dependency injection
  routers/         - Route handlers (one module per resource)
  services/        - Background services and business logic
    rsn_cascade.py   - Cascades RSN renames across stat collections
    name_change.py   - Polls Wise Old Man API for approved name changes
    connection_manager.py - WebSocket connection management
  internal/        - Internal utilities
  tests/           - Test suite
```

---

## Testing

No running database or external services required. Tests use mocked dependencies.

```bash
uv run pytest                          # full suite
uv run pytest -q                       # quiet (dots only)
uv run pytest -v                       # verbose (test names)
uv run pytest app/tests/test_auth.py   # single file
uv run pytest -k "staff"               # tests matching a keyword
uv run pytest --tb=short               # short tracebacks on failure
```

Test files live in `app/tests/`. Each maps to a router:

| File | Covers |
|---|---|
| `test_auth.py` | `/auth/*` - login, OAuth callback, JWT token |
| `test_assets.py` | `/assets/*` - file upload/serve/delete |
| `test_badges.py` | `/badges/*` - badge CRUD and assignments |
| `test_clan.py` | `/clan/*` - stats, leaderboards, name changes |
| `test_clan_competitions.py` | `/clan/competitions/*` - competition CRUD |
| `test_clan_schedules.py` | `/clan/competition-schedules/*` |
| `test_config.py` | `/config/*` - all config GET/PUT pairs |
| `test_content.py` | `/content/*` - categories, entries, versions, reactions |
| `test_discord_routes.py` | `/discord/*` - channels, roles, emojis, members |
| `test_events.py` | `/ccingest` - clan chat ingest webhook |
| `test_feedback.py` | `/feedback/*` - feedback items and replies |
| `test_frenzy.py` | `/frenzy/*` - events, templates, submissions |
| `test_health.py` | `/health` |
| `test_members.py` | `/members/me/*` - accounts, API keys, feed |
| `test_metrics.py` | `/metrics/*`, `/services/*` |
| `test_parties.py` | `/parties/*` - party CRUD, membership, chat |
| `test_ranking.py` | `/ranking/*` - player lookup, admin rebuild |
| `test_role_panels.py` | `/role-panels/*` |
| `test_staff.py` | `/staff/*` - member/ticket overview |
| `test_surveys.py` | `/surveys/*` - survey CRUD, responses |
| `test_tickets.py` | `/tickets/config/*` |

### Test fixtures

Three HTTP client fixtures cover the main permission tiers:

- `anon_client` - sends an invalid Bearer token; protected endpoints return 401
- `auth_client` - authenticated regular user; write operations return 403 by default
- `staff_client` - authenticated user with all permissions bypassed

---

## Development

```bash
uv run ruff check .
uv run ruff format .
```
