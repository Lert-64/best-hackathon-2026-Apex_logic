from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.backend.dependencies import db_dep, require_role
from app.models.audit_log_model import AuditLogs
from app.models.user_model import UserRole
from app.schemas.anomaly_schemas import AuditLogResponse

router = APIRouter(prefix="/api", tags=["Audit Logs"])


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    db: db_dep,
    _=Depends(require_role(UserRole.ADMIN)),
):
    stmt = select(AuditLogs).order_by(AuditLogs.timestamp.desc())
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return [
        AuditLogResponse(
            id=log.lid,
            anomaly_id=log.anomaly_id,
            user_id=log.user_id,
            action=log.action,
            reason=log.reason,
            timestamp=log.timestamp,
        )
        for log in logs
    ]

