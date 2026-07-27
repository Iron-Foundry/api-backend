from fastapi import APIRouter

from ._helpers import _ALL_SERVICE_KEYS, get_service_toggles
from .ballot_tokens import router as ballot_tokens_router
from .discord_features import router as discord_features_router
from .general import router as general_router
from .panel_config import router as panel_config_router
from .ranking import router as ranking_router
from .service_toggles import router as service_toggles_router
from .ticket_features import router as ticket_features_router

__all__ = ["_ALL_SERVICE_KEYS", "get_service_toggles", "router"]

router = APIRouter(prefix="/config", tags=["config"])
router.include_router(general_router)
router.include_router(discord_features_router)
router.include_router(ranking_router)
router.include_router(service_toggles_router)
router.include_router(ticket_features_router)
router.include_router(panel_config_router)
router.include_router(ballot_tokens_router)
