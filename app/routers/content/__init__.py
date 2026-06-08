from fastapi import APIRouter

from .categories import router as categories_router
from .deprecated import router as deprecated_router
from .entries import router as entries_router
from .entry_mutations import router as mutations_router
from .reactions import router as reactions_router
from .versions import router as versions_router

router = APIRouter(prefix="/content", tags=["content"])
# /deprecated-entries must be registered before /{page_type}/... to avoid shadowing
router.include_router(deprecated_router)
router.include_router(categories_router)
router.include_router(entries_router)
router.include_router(mutations_router)
router.include_router(versions_router)
router.include_router(reactions_router)
