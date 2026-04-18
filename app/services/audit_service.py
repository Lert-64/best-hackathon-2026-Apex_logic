from decimal import Decimal

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_model import Anomalies, AnomalyStatus, AnomalyZone
from app.models.audit_log_model import AuditLogs
from app.models.land_model import LandRecords
from app.models.real_estate_model import RealEstateRecords
from app.schemas.ai_schemas import AiAuditCandidate
from app.services.ai_service import enrich_candidates_with_ai


async def run_fuzzy_matching_audit(db: AsyncSession) -> tuple[list[Anomalies], bool]:

    await db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))

    lands_result = await db.execute(select(LandRecords))
    lands = lands_result.scalars().all()

    anomalies_to_create: list[Anomalies] = []
    ai_candidates: list[AiAuditCandidate] = []

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

        if matched_estate:
            continue

        if "komerc" in purpose or "комерц" in purpose:
            area = Decimal(land.area_ha or 0)
            valuation = Decimal(land.valuation or 0)
            loss = area * valuation * Decimal("0.03")
            zone = AnomalyZone.RED
            fallback_summary = "Created from fuzzy mismatch."
        elif "komunal" in ownership or "комунал" in ownership:
            loss = Decimal("0.00")
            zone = AnomalyZone.GREEN
            fallback_summary = "Created as community investment candidate."
        else:
            continue

        anomaly = Anomalies(
            zone=zone,
            tax_id=land.tax_id,
            land_id=land.lid,
            real_estate_id=None,
            risk_score=0,
            ai_summary=fallback_summary,
            ai_decision_confidence=None,
            potential_loss_uah=loss,
            status=AnomalyStatus.PENDING_ADMIN,
        )
        anomalies_to_create.append(anomaly)

        ai_candidates.append(
            AiAuditCandidate(
                zone=zone.value,
                tax_id=land.tax_id,
                purpose=land.purpose,
                ownership_type=land.ownership_type,
                location=land.location,
                potential_loss_uah=float(loss),
            )
        )

    ai_result = await enrich_candidates_with_ai(ai_candidates, batch_size=5)
    for anomaly, profile in zip(anomalies_to_create, ai_result.profiles):
        anomaly.risk_score = profile.risk_score
        anomaly.ai_summary = profile.ai_summary
        anomaly.ai_decision_confidence = profile.decision_confidence

    if anomalies_to_create:
        db.add_all(anomalies_to_create)
        await db.flush()

        creation_logs = [
            AuditLogs(
                anomaly_id=anomaly.lid,
                user_id=None,
                action="PENDING_ADMIN",
                reason="Anomaly created by audit and sent to admin review",
            )
            for anomaly in anomalies_to_create
        ]
        db.add_all(creation_logs)
        await db.commit()

    return anomalies_to_create, ai_result.used_remote_ai
