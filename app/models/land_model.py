import uuid
from typing import Optional
from datetime import date
from decimal import Decimal
from sqlalchemy import String, Date, Text, DECIMAL
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.backend.database import Base


class LandRecords(Base):
    __tablename__ = "land_records"

    lid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cadastral_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    koatuu: Mapped[str] = mapped_column(String)
    ownership_type: Mapped[str] = mapped_column(String)
    purpose: Mapped[str] = mapped_column(String)
    location: Mapped[str] = mapped_column(Text)
    agri_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    area_ha: Mapped[Decimal] = mapped_column(DECIMAL(10, 4))
    valuation: Mapped[Decimal] = mapped_column(DECIMAL(15, 4))
    tax_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    owner_name: Mapped[str] = mapped_column(String)
    ownership_share: Mapped[str] = mapped_column(String)
    reg_date: Mapped[date] = mapped_column(Date)
    record_number: Mapped[str] = mapped_column(String)
    reg_authority: Mapped[str] = mapped_column(String)
    doc_type: Mapped[str] = mapped_column(String)
    doc_subtype: Mapped[Optional[str]] = mapped_column(String, nullable=True)