from pydantic import BaseModel, Field


class AiAuditCandidate(BaseModel):
    zone: str
    tax_id: str | None = None
    purpose: str | None = None
    ownership_type: str | None = None
    location: str | None = None
    potential_loss_uah: float | None = None


class AiAnomalyProfile(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    ai_summary: str
    decision_confidence: int = Field(default=50, ge=0, le=100)
