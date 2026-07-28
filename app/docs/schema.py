"""OpenAPI document customization FastAPI has no constructor argument for."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from .tags import TAG_GROUPS

# Hardcoded rather than read from the environment: these land in the committed
# openapi.json, which the contract test compares byte for byte. An env-derived
# value would make that artifact differ per machine.
SERVERS: list[dict[str, Any]] = [
    {"url": "https://api.ironfoundry.cc", "description": "Production"},
    {"url": "http://localhost:8000", "description": "Local development"},
]


def install_openapi_customization(app: FastAPI) -> None:
    """Emit `x-tagGroups` so the reference groups its tags into sections."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
            servers=app.servers,
            separate_input_output_schemas=app.separate_input_output_schemas,
        )
        schema["x-tagGroups"] = TAG_GROUPS
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
