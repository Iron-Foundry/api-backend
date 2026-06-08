from fastapi import APIRouter

from .management import router as management_router
from .public import router as public_router
from .responses import router as responses_router

router = APIRouter(prefix="/surveys", tags=["surveys"])
# management POST "" must come before public GET "" to avoid ambiguity
router.include_router(management_router)
router.include_router(responses_router)
router.include_router(public_router)
