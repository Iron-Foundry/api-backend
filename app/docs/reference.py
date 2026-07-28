"""Scalar API reference page: branding and client behaviour."""

from __future__ import annotations

import os

from fastapi.responses import HTMLResponse
from scalar_fastapi import get_scalar_api_reference

_FRONTEND_URL = (
    os.getenv("FRONTEND_URL", "http://localhost:5173").split(",")[0].strip().rstrip("/")
)

_CUSTOM_CSS = """
.dark-mode {
  --scalar-background-1: hsl(222 20% 10%);
  --scalar-background-2: hsl(222 18% 14%);
  --scalar-background-3: hsl(222 15% 18%);
  --scalar-background-accent: hsl(42 80% 55% / 0.12);
  --scalar-color-1: hsl(40 15% 88%);
  --scalar-color-2: hsl(220 10% 65%);
  --scalar-color-3: hsl(220 10% 55%);
  --scalar-color-accent: hsl(42 80% 55%);
  --scalar-border-color: hsl(222 15% 20%);
  --scalar-button-1: hsl(42 80% 55%);
  --scalar-button-1-color: hsl(222 20% 10%);
  --scalar-button-1-hover: hsl(42 80% 62%);
}
.light-mode {
  --scalar-background-1: hsl(36 22% 87%);
  --scalar-background-2: hsl(36 16% 82%);
  --scalar-background-3: hsl(36 16% 78%);
  --scalar-background-accent: hsl(42 88% 81% / 0.5);
  --scalar-color-1: hsl(220 18% 18%);
  --scalar-color-2: hsl(210 15% 38%);
  --scalar-color-3: hsl(210 15% 48%);
  --scalar-color-accent: hsl(42 58% 42%);
  --scalar-border-color: hsl(205 22% 70%);
  --scalar-button-1: hsl(42 58% 42%);
  --scalar-button-1-color: hsl(36 22% 95%);
  --scalar-button-1-hover: hsl(42 58% 36%);
}
.dark-mode .t-doc__sidebar,
.light-mode .t-doc__sidebar {
  --scalar-sidebar-background-1: var(--scalar-background-2);
  --scalar-sidebar-border-color: var(--scalar-border-color);
  --scalar-sidebar-color-1: var(--scalar-color-1);
  --scalar-sidebar-color-2: var(--scalar-color-2);
  --scalar-sidebar-color-active: var(--scalar-color-accent);
  --scalar-sidebar-item-hover-background: var(--scalar-background-3);
  --scalar-sidebar-item-active-background: var(--scalar-background-accent);
  --scalar-sidebar-search-background: var(--scalar-background-1);
  --scalar-sidebar-search-border-color: var(--scalar-border-color);
}
:root {
  --scalar-radius: 0.5rem;
  --scalar-radius-lg: 0.5rem;
  --scalar-radius-xl: 0.75rem;
}
"""


def render_reference(openapi_url: str, title: str) -> HTMLResponse:
    """Render the Scalar reference page for the given OpenAPI document."""
    return get_scalar_api_reference(
        openapi_url=openapi_url,
        title=title,
        scalar_favicon_url=f"{_FRONTEND_URL}/logo-320.png",
        custom_css=_CUSTOM_CSS,
        dark_mode=True,
        persist_auth=True,
        authentication={"preferredSecurityScheme": "DiscordJWT"},
        telemetry=False,
    )
