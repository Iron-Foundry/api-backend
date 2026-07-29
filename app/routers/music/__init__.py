from fastapi import APIRouter

from app.docs import responses

from .bot import router as bot_router
from .control import router as control_router
from .importing import router as import_router
from .live import router as live_router
from .playlists import router as playlists_router
from .search import router as search_router
from .sessions import router as sessions_router
from .stats import router as stats_router

router = APIRouter(
    prefix="/music", tags=["music"], responses=responses.AUTHENTICATED_LOOKUP
)
# The service-key surface is mounted first: its paths start with a literal
# segment, so it can never be shadowed by /playlists/{playlist_id}.
router.include_router(bot_router)
router.include_router(search_router)
router.include_router(stats_router)
router.include_router(live_router)
router.include_router(sessions_router)
router.include_router(control_router)
# Before the playlist router, so /playlists/import is matched as a literal
# rather than tried as a {playlist_id}.
router.include_router(import_router)
router.include_router(playlists_router)
