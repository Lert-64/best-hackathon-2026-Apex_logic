from decimal import Decimal
import re
from difflib import SequenceMatcher

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_model import Anomalies, AnomalyStatus, AnomalyZone
from app.models.audit_log_model import AuditLogs
from app.models.land_model import LandRecords
from app.models.real_estate_model import RealEstateRecords
from app.schemas.ai_schemas import AiAuditCandidate
from app.services.ai_service import enrich_candidates_with_ai


UNKNOWN_OWNER_VALUES = {"", "unknown", "unknown_owner", "невідомо"}
UNKNOWN_LOCATION_VALUES = {"", "unknown", "невідомо"}


def _normalize_text(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _is_unknown_owner(value: str | None) -> bool:
    return _normalize_text(value) in UNKNOWN_OWNER_VALUES


def _is_meaningful_location(value: str | None) -> bool:
    return _normalize_text(value) not in UNKNOWN_LOCATION_VALUES


def _owner_similarity(left: str | None, right: str | None) -> float:
    a = _normalize_text(left)
    b = _normalize_text(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(a=a, b=b).ratio()


def _calc_loss(area_ha: Decimal | None, valuation: Decimal | None) -> Decimal:
    area = Decimal(area_ha or 0)
    valuation_value = Decimal(valuation or 0)
    return area * valuation_value * Decimal("0.03")


async def run_fuzzy_matching_audit(db: AsyncSession) -> tuple[list[Anomalies], bool]:

    await db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))

    lands_result = await db.execute(select(LandRecords))
    lands = lands_result.scalars().all()

    anomalies_to_create: list[Anomalies] = []
    ai_candidates: list[AiAuditCandidate] = []

    for land in lands:
        matched_estate: RealEstateRecords | None = None
        trigger_reason: str | None = None
        zone = AnomalyZone.GREEN
        loss = Decimal("0.00")

        # Prefer a direct identifier match for this dataset shape.
        if land.tax_id:
            estate_by_tax = await db.execute(select(RealEstateRecords).where(RealEstateRecords.tax_id == land.tax_id))
            matched_estate = estate_by_tax.scalars().first()

        # Fallback to legacy fuzzy lookup only when direct identifier match is unavailable.
        if not matched_estate and land.tax_id and _is_meaningful_location(land.location):
            stmt = select(RealEstateRecords).where(
                RealEstateRecords.tax_id == land.tax_id,
                or_(
                    RealEstateRecords.cadastral_number == land.cadastral_number,
                    func.similarity(land.location, RealEstateRecords.address) > 0.4,
                ),
            )
            estate_result = await db.execute(stmt)
            matched_estate = estate_result.scalars().first()

        if not land.tax_id:
            trigger_reason = "Missing tax id in land register record."
            zone = AnomalyZone.RED
        elif not matched_estate:
            trigger_reason = "No matching real estate record by tax id/fuzzy criteria."
            zone = AnomalyZone.RED
            loss = _calc_loss(land.area_ha, land.valuation)
        else:
            owner_similarity = _owner_similarity(land.owner_name, matched_estate.owner_name)
            if _is_unknown_owner(land.owner_name) or _is_unknown_owner(matched_estate.owner_name):
                trigger_reason = "Owner name missing in one of the matched records."
                zone = AnomalyZone.GREEN
            elif owner_similarity < 0.72:
                trigger_reason = (
                    "Owner names differ between matched records "
                    f"(similarity={owner_similarity:.2f})."
                )
                zone = AnomalyZone.GREEN

        if not trigger_reason:
            continue

        anomaly = Anomalies(
            zone=zone,
            tax_id=land.tax_id,
            land_id=land.lid,
            real_estate_id=matched_estate.lid if matched_estate else None,
            risk_score=0,
            ai_summary=trigger_reason,
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
