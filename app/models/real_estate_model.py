import uuid
from typing import Optional
from datetime import date
from decimal import Decimal
from sqlalchemy import String, Date, Text, DECIMAL
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.backend.database import Base


class  RealEstateRecords(Base):
    __tablename__ = "real_estate_records"

    lid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tax_id: Mapped[str] = mapped_column(String, index=True)
    owner_name: Mapped[str] = mapped_column(String)
    object_type: Mapped[str] = mapped_column(String)
    address: Mapped[str] = mapped_column(Text)
    cadastral_number: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    reg_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    termination_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    total_area_sqm: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))
    joint_ownership_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ownership_share: Mapped[Optional[str]] = mapped_column(String, nullable=True)