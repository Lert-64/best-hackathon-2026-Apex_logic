from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import List
from uuid import UUID

from app.backend.dependencies import db_dep, get_current_user, require_role
from app.models.user_model import User, UserRole
from app.models.anomaly_model import Anomalies, AnomalyStatus
from app.models.audit_log_model import AuditLog
from app.schemas.anomaly_schemas import (
    AnomalyResponse,
    AnomalyStatusUpdate,
    AssignInspectorRequest,
    InspectorReportSubmit,
)

router = APIRouter(prefix="/api/anomalies", tags=["Anomalies"])


class AnomalyStats(BaseModel):
    total_anomalies: int
    total_potential_loss: float
    status_counts: dict


@router.get("/stats", response_model=AnomalyStats)
async def get_stats(db: db_dep, current_user: User = Depends(require_role(UserRole.ADMIN))):
    total_q = await db.execute(select(func.count(Anomaly.lid)))
    total = total_q.scalar() or 0

    loss_q = await db.execute(select(func.sum(Anomaly.potential_loss_uah)))
    loss = loss_q.scalar() or 0.0

    status_q = await db.execute(select(Anomaly.status, func.count(Anomaly.lid)).group_by(Anomaly.status))
    status_counts = {row[0].value: row[1] for row in status_q.all()}

    return AnomalyStats(total_anomalies=total, total_potential_loss=float(loss), status_counts=status_counts)


@router.get("/", response_model=List[AnomalyResponse])
async def get_anomalies(db: db_dep, current_user: User = Depends(get_current_user),
                        status: AnomalyStatus | None = None):
    query = select(Anomaly)
    if status:
        query = query.where(Anomaly.status == status)
    if current_user.role == UserRole.INSPECTOR:
        query = query.where(Anomaly.inspector_id == current_user.id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{anomaly_id}", response_model=AnomalyResponse)
async def get_anomaly(anomaly_id: UUID, db: db_dep, current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Anomaly).where(Anomaly.lid == anomaly_id))
    anomaly = result.scalar_one_or_none()
    if not anomaly:
        raise HTTPException(status_code=404)
    return anomaly


@router.post("/{anomaly_id}/assign", response_model=AnomalyResponse)
async def assign_inspector(anomaly_id: UUID, req: AssignInspectorRequest, db: db_dep,
                           current_user: User = Depends(require_role(UserRole.ADMIN))):
    result = await db.execute(select(Anomaly).where(Anomaly.lid == anomaly_id))
    anomaly = result.scalar_one_or_none()
    if not anomaly:
        raise HTTPException(status_code=404)

    old_status = anomaly.status
    anomaly.inspector_id = req.inspector_id
    anomaly.inspector_instruction = req.instruction
    anomaly.status = AnomalyStatus.IN_WORK

    log = AuditLog(anomaly_id=anomaly.lid, user_id=current_user.id, action="ASSIGN_INSPECTOR", old_status=old_status,
                   new_status=anomaly.status)
    db.add(log)
    await db.commit()
    await db.refresh(anomaly)
    return anomaly


@router.patch("/{anomaly_id}/status", response_model=AnomalyResponse)
async def update_status(anomaly_id: UUID, req: AnomalyStatusUpdate, db: db_dep,
                        current_user: User = Depends(require_role(UserRole.ADMIN))):
    result = await db.execute(select(Anomaly).where(Anomaly.lid == anomaly_id))
    anomaly = result.scalar_one_or_none()
    if not anomaly:
        raise HTTPException(status_code=404)

    old_status = anomaly.status
    anomaly.status = req.status

    log = AuditLog(anomaly_id=anomaly.lid, user_id=current_user.id, action="UPDATE_STATUS", old_status=old_status,
                   new_status=anomaly.status, comment=req.reason)
    db.add(log)
    await db.commit()
    await db.refresh(anomaly)
    return anomaly


@router.post("/{anomaly_id}/report", response_model=AnomalyResponse)
async def submit_report(anomaly_id: UUID, req: InspectorReportSubmit, db: db_dep,
                        current_user: User = Depends(require_role(UserRole.INSPECTOR))):
    result = await db.execute(select(Anomaly).where(Anomaly.lid == anomaly_id))
    anomaly = result.scalar_one_or_none()
    if not anomaly:
        raise HTTPException(status_code=404)
    if anomaly.inspector_id != current_user.id:
        raise HTTPException(status_code=403)

    old_status = anomaly.status
    anomaly.inspector_comment = req.inspector_comment
    anomaly.status = AnomalyStatus.RESOLVED if req.is_confirmed else AnomalyStatus.DISMISSED

    log = AuditLog(anomaly_id=anomaly.lid, user_id=current_user.id, action="SUBMIT_REPORT", old_status=old_status,
                   new_status=anomaly.status, comment=req.inspector_comment)
    db.add(log)
    await db.commit()
    await db.refresh(anomaly)
    return anomaly