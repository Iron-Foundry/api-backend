from fastapi import APIRouter

from .endpoints import router as endpoints_router

router = APIRouter(prefix="/tickets", tags=["ticket-config"])
router.include_router(endpoints_router)
