from fastapi import APIRouter

from app.docs import responses

from .endpoints import router as endpoints_router

router = APIRouter(
    prefix="/tickets", tags=["ticket-config"], responses=responses.STAFF_LOOKUP
)
router.include_router(endpoints_router)
