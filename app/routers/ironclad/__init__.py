from fastapi import APIRouter

from .deaths import router as deaths_router

router = APIRouter(prefix="/ironclad", tags=["ironclad"])
router.include_router(deaths_router, prefix="/sanitize")
