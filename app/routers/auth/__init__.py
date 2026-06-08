from fastapi import APIRouter

from .discord_oauth import router as oauth_router
from .session import router as session_router

router = APIRouter(prefix="/auth", tags=["auth"])
router.include_router(oauth_router)
router.include_router(session_router)
