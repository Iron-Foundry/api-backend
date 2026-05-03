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

## Development

```bash
uv run ruff check .
uv run ruff format .
```
