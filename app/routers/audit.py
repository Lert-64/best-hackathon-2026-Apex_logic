from fastapi import APIRouter, Depends, File, UploadFile

from app.backend.dependencies import db_dep, require_role
from app.models.user_model import UserRole
from app.services.audit_service import run_fuzzy_matching_audit
from app.services.import_service import import_registers

router = APIRouter(prefix="/data", tags=["Audit Core"])


@router.post("/upload-registers")
async def upload_registers(
    db: db_dep,
    land_file: UploadFile = File(...),
    real_estate_file: UploadFile = File(...),
    _=Depends(require_role(UserRole.ADMIN)),
):
    """Upload land + real estate registries as CSV/XLSX files."""

    result = await import_registers(db, land_file=land_file, real_estate_file=real_estate_file)
    return {
        "message": "Registers uploaded",
        **result,
    }


@router.post("/run-audit")
async def execute_audit(
    db: db_dep,
    _=Depends(require_role(UserRole.ADMIN)),
):
    """Run matching audit and return a compact result payload."""

    anomalies, used_remote_ai = await run_fuzzy_matching_audit(db)

    red_count = sum(1 for anomaly in anomalies if anomaly.zone.value == "RED")
    green_count = sum(1 for anomaly in anomalies if anomaly.zone.value == "GREEN")

    return {
        "message": "Audit completed",
        "created": len(anomalies),
        "red": red_count,
        "green": green_count,
        "status": "PENDING_ADMIN",
        "ai_enriched": len(anomalies),
        "used_remote_ai": used_remote_ai,
    }

