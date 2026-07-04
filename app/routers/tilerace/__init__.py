from fastapi import APIRouter

from .controls import router as controls_router
from .events import router as events_router
from .osrs_ref import router as osrs_ref_router
from .repository import router as repository_router
from .teams import router as teams_router

router = APIRouter(prefix="/tilerace", tags=["tilerace"])

router.include_router(events_router)
router.include_router(osrs_ref_router)
router.include_router(repository_router)
router.include_router(teams_router)
router.include_router(controls_router)
