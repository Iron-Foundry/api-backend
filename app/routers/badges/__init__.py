from fastapi import APIRouter

from .assignments import router as assignments_router
from .crud import router as crud_router

router = APIRouter(prefix="/badges", tags=["badges"])

# /me must be registered before /{badge_id} to avoid route shadowing
router.include_router(assignments_router)
router.include_router(crud_router)
