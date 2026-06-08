from fastapi import APIRouter

from ._osrs_cache import warm_osrs_caches as warm_osrs_caches
from .events import router as events_router
from .history import router as history_router
from .osrs_ref import router as osrs_ref_router
from .public import router as public_router
from .submissions import router as submissions_router
from .teams import router as teams_router
from .templates import router as templates_router

router = APIRouter(prefix="/frenzy", tags=["frenzy"])

# Public routes first
router.include_router(public_router)
router.include_router(history_router)
router.include_router(osrs_ref_router)

# Admin routes
router.include_router(templates_router)
router.include_router(events_router)
router.include_router(teams_router)
router.include_router(submissions_router)
