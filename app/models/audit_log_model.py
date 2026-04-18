import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.backend.database import Base


class AuditLogs(Base):
    __tablename__ = "audit_logs"

    lid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    anomaly_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("anomalies.lid"))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)  # Null = Система
    action: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)