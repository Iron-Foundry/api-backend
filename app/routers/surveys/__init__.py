from fastapi import APIRouter

# Aliased: importing the sibling .responses submodule below rebinds the bare
# name `responses` on this package, shadowing the app.docs import.
from app.docs import responses as doc_responses

from .management import router as management_router
from .public import router as public_router
from .responses import router as responses_router

router = APIRouter(
    prefix="/surveys", tags=["surveys"], responses=doc_responses.AUTHENTICATED_LOOKUP
)
# management POST "" must come before public GET "" to avoid ambiguity
router.include_router(management_router)
router.include_router(responses_router)
router.include_router(public_router)
