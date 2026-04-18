import uuid
import enum
from typing import Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, ForeignKey, DateTime, Enum as SQLEnum, Text, DECIMAL
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.backend.database import Base

class AnomalyZone(str, enum.Enum):
    RED = "RED"
    GREEN = "GREEN"

class AnomalyStatus(str, enum.Enum):
    PENDING_ADMIN = "PENDING_ADMIN"
    NEW = "NEW"
    IN_WORK = "IN_WORK"
    PENDING_INSPECTOR = "PENDING_INSPECTOR"
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
    status: Mapped[AnomalyStatus] = mapped_column(SQLEnum(AnomalyStatus), default=AnomalyStatus.PENDING_ADMIN)

    volunteer_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    volunteer_photo_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    volunteer_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    inspector_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    inspector_instruction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    inspector_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    
    land_record: Mapped["LandRecords"] = relationship()
    real_estate_record: Mapped[Optional["RealEstateRecords"]] = relationship()
    volunteer: Mapped[Optional["User"]] = relationship(foreign_keys=[volunteer_id])
    inspector: Mapped[Optional["User"]] = relationship(foreign_keys=[inspector_id])
