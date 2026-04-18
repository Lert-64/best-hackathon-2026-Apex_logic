from fastapi import APIRouter

from .audit import router as audit_router
from .audit_logs import router as audit_logs_router
from .auth_router import router as auth_router
from .anomalies import router as anomalies_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(audit_router)
router.include_router(anomalies_router)
router.include_router(audit_logs_router)
