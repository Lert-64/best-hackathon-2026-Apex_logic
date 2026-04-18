from fastapi import APIRouter

from .audit import router as audit_router
from .auth_router import router as auth_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(audit_router)
