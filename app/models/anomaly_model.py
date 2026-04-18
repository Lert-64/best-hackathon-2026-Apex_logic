import uuid
import enum
from typing import Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, ForeignKey, DateTime, Enum as SQLEnum, Text, DECIMAL
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.backend.database import Base
from app.models.anomaly_model import AnomalyZone, AnomalyStatus





class AnomalyZone(str, enum.Enum):
    RED = "RED"
    GREEN = "GREEN"

class AnomalyStatus(str, enum.Enum):
    NEW = "NEW"
    IN_WORK = "IN_WORK"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"



class Anomalies(Base):
    __tablename__ = "anomalies"

    lid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone: Mapped[AnomalyZone] = mapped_column(SQLEnum(AnomalyZone), index=True)
    tax_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)

    land_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("land_records.lid"))
    real_estate_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("real_estate_records.lid"), nullable=True)

    risk_score: Mapped[int] = mapped_column(Integer)
    ai_summary: Mapped[str] = mapped_column(Text)
    potential_loss_uah: Mapped[Decimal] = mapped_column(DECIMAL(15, 2))
    status: Mapped[AnomalyStatus] = mapped_column(SQLEnum(AnomalyStatus), default=AnomalyStatus.NEW)

    inspector_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    inspector_instruction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    inspector_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    
    land_record: Mapped["LandRecord"] = relationship()
    real_estate_record: Mapped[Optional["RealEstateRecord"]] = relationship()
    inspector: Mapped[Optional["User"]] = relationship()