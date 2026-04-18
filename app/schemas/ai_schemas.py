from pydantic import BaseModel, Field

class AiAnomalyProfile(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    ai_summary: str


