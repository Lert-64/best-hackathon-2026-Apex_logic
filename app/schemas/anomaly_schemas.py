from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional
from app.models.enums import AnomalyZone, AnomalyStatus

class AnomalyResponse(BaseModel):
    id: UUID
    zone: AnomalyZone
    tax_id: Optional[str] = None
    owner_name: Optional[str] = None
    cadastral_number: str
    potential_loss_uah: Optional[float] = None
    risk_score: Optional[int] = None
    ai_summary: Optional[str] = None
    status: AnomalyStatus
    created_at: datetime

class AnomalyStatusUpdate(BaseModel):
    status: AnomalyStatus
    reason: str = Field(min_length=5)

class AssignInspectorRequest(BaseModel):
    inspector_id: UUID
    instruction: str

class InspectorReportSubmit(BaseModel):
    is_confirmed: bool
    inspector_comment: str