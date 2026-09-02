# Iron Foundry - API Backend

REST API backend for the Iron Foundry platform. Built with FastAPI and served by Gunicorn.

---

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (package manager)
- A running PostgreSQL instance and a running Valkey/Redis instance

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
| `DATABASE_URL` | Yes | - | PostgreSQL connection URI (`postgresql+asyncpg://...`) |
| `VALKEY_URI` | Yes | `redis://localhost:6379` | Valkey/Redis connection URI |
| `JWT_SECRET` | Yes | `change-me` | HS256 signing secret for issued tokens |
| `DISCORD_CLIENT_ID` | Yes | - | Discord OAuth2 application ID |
| `DISCORD_CLIENT_SECRET` | Yes | - | Discord OAuth2 application secret |
| `DISCORD_TOKEN` | Yes | - | Bot token used for guild lookups |
| `GUILD_ID` | Yes | - | The ID of the Discord server |
| `FRONTEND_URL` | No | `https://ironfoundry.cc` | Allowed CORS origins, comma-separated |
| `STAFF_ROLE_ID` / `SENIOR_STAFF_ROLE_ID` / `OWNER_ROLE_ID` / `MENTOR_ROLE_ID` | Yes | - | Permission tier role IDs |
| `UPLOAD_DIR` | No | `/app/uploads` | Asset storage directory |
| `OSRS_CACHE_SERVICE_URL` | No | `http://osrs-cache-service:8100` | Internal osrs-cache-service base URL |
| `MAP_TILES_BASE_URL` | No | - | Public base URL of the `cache-tiles` nginx sidecar |
| `METRICS_API_KEY` | No | - | Shared service key accepted on metrics ingest |
| `LAVALINK_URI` / `LAVALINK_PASSWORD` | No | - | Lavalink node, for the music bridge |
| `WOM_GROUP_ID` | No | - | Wise Old Man group ID - enables RSN name change tracking when set |
| `WOM_GROUP_KEY` | No | - | WOM group token (private groups only) |
| `WOM_API_KEY` | No | - | WOM API key |
| `WOM_CLAN_NAME` | No | `Iron Foundry` | Must match `clan_name` in stat records |

---

## Structure

```
app/
  main.py          - FastAPI application entry point, lifespan, background tasks
  dependencies.py  - Shared dependency injection
  version.py       - Build metadata (GIT_SHA / BUILD_TIME)
  routers/         - Route handlers (one package or module per resource)
  services/        - Background services and business logic
    name_change.py        - Polls the Wise Old Man API for approved name changes
    clan_stats.py         - Clan stat aggregation
    ranking_service/      - Rank calculation and rebuilds
    connection_manager.py - WebSocket connection management
    music_*.py            - Music bridge, live state, and stats
  db/models/       - SQLAlchemy models
  models/          - Pydantic request/response schemas
  party_store/     - Party state persistence
  docs/            - Scalar API reference assets
  tests/           - Test suite
alembic/versions/  - Database migrations
```

The OpenAPI document is generated, not hand-written:

```bash
uv run python scripts/generate_openapi.py   # regenerates openapi.json
```

---

## Testing

The default run needs no database or external services - `addopts = "-m 'not integration'"`
deselects the real-infra tests and everything else uses mocked dependencies.

```bash
uv run pytest                          # default suite (integration deselected)
uv run pytest -m integration           # real-infra tests (Postgres + Valkey containers)
uv run pytest app/tests/test_auth.py   # single file
uv run pytest -k "staff"               # tests matching a keyword
uv run pytest --tb=short               # short tracebacks on failure
```

Test files live in `app/tests/`, one per router (`test_<resource>.py` covers
`/<resource>/*` - `test_auth.py` for `/auth/*`, `test_parties.py` for `/parties/*`, and
so on). Every endpoint has a test; a new router ships with its test file in the same
change. Alongside those:

| File | Covers |
|---|---|
| `test_openapi_contract.py` / `test_openapi_metadata.py` | `openapi.json` matches the live app |
| `test_inbound_contracts.py` | payloads the discord bots post to this API |
| `test_outbound_metrics.py` | metrics this API reports onward |
| `test_smoke.py` / `test_health.py` | app boot and `/health` |
| `app/tests/integration/` | real Postgres/Valkey journeys, marked `integration` |

### Test fixtures

Three HTTP client fixtures cover the main permission tiers:

- `anon_client` - sends an invalid Bearer token; protected endpoints return 401
- `auth_client` - authenticated regular user; write operations return 403 by default
- `staff_client` - authenticated user with all permissions bypassed

---

## Development

```bash
uv run ruff format .
uv run ruff check . --fix
uv run pyright
```

Pre-commit hooks (`.pre-commit-config.yaml`) run Ruff lint and format on commit.
From the monorepo root, `./run-tests.sh {lint|fast|integration|e2e|all}` runs this
module alongside the other services.
