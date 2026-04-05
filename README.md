# Iron Foundry — API Backend

REST API backend for the Iron Foundry platform. Built with FastAPI and served by Gunicorn.

> **Status:** Early development — project structure is scaffolded, endpoints are not yet implemented.

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

## Structure

```
app/
  main.py          — FastAPI application entry point
  dependencies.py  — Shared dependency injection
  routers/         — Route handlers (one module per resource)
  internal/        — Internal utilities
  tests/           — Test suite
```

---

## Development

```bash
uv run ruff check .
uv run ruff format .
```
