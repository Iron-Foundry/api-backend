from fastapi import APIRouter

from .members import router as members_router
from .overview import router as overview_router
from .rsn import router as rsn_router
from .tickets import router as tickets_router

router = APIRouter(prefix="/staff", tags=["staff"])
router.include_router(overview_router)
router.include_router(members_router)
router.include_router(rsn_router)
router.include_router(tickets_router)
