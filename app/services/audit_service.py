from decimal import Decimal

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_model import Anomalies, AnomalyStatus, AnomalyZone
from app.models.land_model import LandRecords
from app.models.real_estate_model import RealEstateRecords


async def run_fuzzy_matching_audit(db: AsyncSession) -> list[Anomalies]:
    """Run rule-based matching between land records and real estate records."""

    # Enable trigram extension for similarity search in PostgreSQL.
    await db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))

    lands_result = await db.execute(select(LandRecords))
    lands = lands_result.scalars().all()

    anomalies_to_create: list[Anomalies] = []

    for land in lands:
        if not land.tax_id:
            continue

        stmt = select(RealEstateRecords).where(
            RealEstateRecords.tax_id == land.tax_id,
            or_(
                RealEstateRecords.cadastral_number == land.cadastral_number,
                func.similarity(land.location, RealEstateRecords.address) > 0.4,
            ),
        )
        estate_result = await db.execute(stmt)
        matched_estate = estate_result.scalars().first()

        purpose = (land.purpose or "").lower()
        ownership = (land.ownership_type or "").lower()

        if "комерц" in purpose and not matched_estate:
            area = Decimal(land.area_ha or 0)
            valuation = Decimal(land.valuation or 0)
            loss = area * valuation * Decimal("0.03")

            anomalies_to_create.append(
                Anomalies(
                    zone=AnomalyZone.RED,
                    tax_id=land.tax_id,
                    land_id=land.lid,
                    real_estate_id=None,
                    risk_score=0,
                    ai_summary="Auto-detected by fuzzy matching audit.",
                    potential_loss_uah=loss,
                    status=AnomalyStatus.NEW,
                )
            )
        elif "комунал" in ownership and not matched_estate:
            anomalies_to_create.append(
                Anomalies(
                    zone=AnomalyZone.GREEN,
                    tax_id=None,
                    land_id=land.lid,
                    real_estate_id=None,
                    risk_score=0,
                    ai_summary="Auto-detected investment opportunity.",
                    potential_loss_uah=Decimal("0.00"),
                    status=AnomalyStatus.NEW,
                )
            )

    if anomalies_to_create:
        db.add_all(anomalies_to_create)
        await db.commit()

    return anomalies_to_create

