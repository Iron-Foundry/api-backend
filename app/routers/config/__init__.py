from fastapi import APIRouter

from .discord_features import router as discord_features_router
from .general import router as general_router
from .ranking import router as ranking_router
from .service_toggles import router as service_toggles_router
from .ticket_features import router as ticket_features_router
from ._helpers import _ALL_SERVICE_KEYS, get_service_toggles

__all__ = ["router", "get_service_toggles", "_ALL_SERVICE_KEYS"]

router = APIRouter(prefix="/config", tags=["config"])
router.include_router(general_router)
router.include_router(discord_features_router)
router.include_router(ranking_router)
router.include_router(service_toggles_router)
router.include_router(ticket_features_router)
