"""HTTP service handlers for external APIs."""

from app.services.http.wiki import OsrsWikiHandler
from app.services.http.wom import WiseOldManHandler

__all__ = ["WiseOldManHandler", "OsrsWikiHandler"]
