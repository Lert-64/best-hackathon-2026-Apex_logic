from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional
from app.models.anomaly_model import AnomalyZone, AnomalyStatus

class AnomalyResponse(BaseModel):
    id: UUID
    zone: AnomalyZone
    tax_id: Optional[str] = None
    owner_name: Optional[str] = None
    cadastral_number: str
    location: Optional[str] = None
    potential_loss_uah: Optional[float] = None
    risk_score: Optional[int] = None
    ai_summary: Optional[str] = None
    ai_decision_confidence: Optional[int] = None
    status: AnomalyStatus
    volunteer_id: Optional[UUID] = None
    volunteer_photo_url: Optional[str] = None
    volunteer_comment: Optional[str] = None
    inspector_id: Optional[UUID] = None
    inspector_comment: Optional[str] = None
    created_at: datetime

class AnomalyStatusUpdate(BaseModel):
    status: AnomalyStatus
    reason: str = Field(min_length=5)


class TakeTaskResponse(BaseModel):
    anomaly_id: UUID
    status: AnomalyStatus

class InspectorReportSubmit(BaseModel):
    is_confirmed: bool
    inspector_comment: Optional[str] = None


class AdminDecisionSubmit(BaseModel):
    is_confirmed: bool
    reason: Optional[str] = None


class AnomalyStatsResponse(BaseModel):
    total: int
    pending_admin: int
    new: int
    in_work: int
    pending_inspector: int
    resolved: int
    dismissed: int


class AuditLogResponse(BaseModel):
    id: UUID
    anomaly_id: UUID
    user_id: Optional[UUID] = None
    action: str
    reason: str
    timestamp: datetime

