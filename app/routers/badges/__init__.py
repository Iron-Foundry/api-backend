from fastapi import APIRouter

from app.docs import responses

from .assignments import router as assignments_router
from .crud import router as crud_router

router = APIRouter(
    prefix="/badges", tags=["badges"], responses=responses.AUTHENTICATED_LOOKUP
)

# /me must be registered before /{badge_id} to avoid route shadowing
router.include_router(assignments_router)
router.include_router(crud_router)
