import asyncio

from fastapi import APIRouter

from app.backend.dependencies import db_dep
from app.services.audit_service import run_fuzzy_matching_audit

router = APIRouter(prefix="/data", tags=["Audit Core"])

# Protect future AI fan-out from provider rate limits.
ai_semaphore = asyncio.Semaphore(5)


@router.post("/run-audit")
async def execute_audit(db: db_dep):
    """Run matching audit and return a compact result payload."""

    anomalies = await run_fuzzy_matching_audit(db)

    red_count = sum(1 for anomaly in anomalies if anomaly.zone.value == "RED")
    green_count = sum(1 for anomaly in anomalies if anomaly.zone.value == "GREEN")

    return {
        "message": "Аудит успішно завершено.",
        "created": len(anomalies),
        "red": red_count,
        "green": green_count,
    }

