"""API reference presentation: intro copy, tag metadata, and schema extensions."""

from . import responses
from .description import DESCRIPTION
from .reference import render_reference
from .schema import SERVERS, install_openapi_customization
from .tags import TAG_GROUPS, TAGS_METADATA

__all__ = [
    "DESCRIPTION",
    "SERVERS",
    "TAGS_METADATA",
    "TAG_GROUPS",
    "install_openapi_customization",
    "render_reference",
    "responses",
]
