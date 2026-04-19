from decimal import Decimal
from datetime import date
import re
from difflib import SequenceMatcher

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_model import Anomalies, AnomalyStatus, AnomalyZone
from app.models.audit_log_model import AuditLogs
from app.models.land_model import LandRecords
from app.models.real_estate_model import RealEstateRecords
from app.schemas.ai_schemas import AiAuditCandidate
from app.services.ai_service import enrich_candidates_with_ai


UNKNOWN_OWNER_VALUES = {"", "unknown", "unknown_owner", "невідомо"}
UNKNOWN_LOCATION_VALUES = {"", "unknown", "невідомо"}
UNKNOWN_TEXT_VALUES = {"", "unknown", "невідомо"}
MISSING_REG_DATE_SENTINEL = date(1900, 1, 1)


def _normalize_text(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _is_unknown_owner(value: str | None) -> bool:
    return _normalize_text(value) in UNKNOWN_OWNER_VALUES


def _is_meaningful_location(value: str | None) -> bool:
    return _normalize_text(value) not in UNKNOWN_LOCATION_VALUES


def _is_unknown_text(value: str | None) -> bool:
    return _normalize_text(value) in UNKNOWN_TEXT_VALUES


def _compute_data_quality_penalty(land: LandRecords) -> tuple[int, list[str]]:
    penalty = 0
    issues: list[str] = []

    if not land.tax_id:
        penalty += 20
        issues.append("missing tax id")
    if _is_unknown_owner(land.owner_name):
        penalty += 8
        issues.append("missing owner name")
    if not _is_meaningful_location(land.location):
        penalty += 8
        issues.append("missing location")
    if land.reg_date <= MISSING_REG_DATE_SENTINEL:
        penalty += 12
        issues.append("missing registration date")
    if (land.record_number or "").startswith("AUTO-REC-"):
        penalty += 10
        issues.append("missing record number")
    if _is_unknown_text(land.reg_authority):
        penalty += 6
        issues.append("missing registration authority")
    if _is_unknown_text(land.doc_type):
        penalty += 6
        issues.append("missing document type")

    return min(penalty, 45), issues


def _owner_similarity(left: str | None, right: str | None) -> float:
    a = _normalize_text(left)
    b = _normalize_text(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(a=a, b=b).ratio()


def _location_similarity(left: str | None, right: str | None) -> float:
    a = _normalize_text(left)
    b = _normalize_text(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(a=a, b=b).ratio()


def _normalize_share(value: str | None) -> str | None:
    text = _normalize_text(value).replace(" ", "")
    if not text or _is_unknown_text(text):
        return None

    if "/" in text:
        parts = text.split("/", 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit() and parts[1] != "0":
            return f"{int(parts[0])}/{int(parts[1])}"

    if text.endswith("%"):
        numeric = text[:-1]
        if numeric.replace(".", "", 1).isdigit():
            return f"{Decimal(numeric).normalize()}%"

    return text


async def _find_best_estate_match(db: AsyncSession, land: LandRecords) -> RealEstateRecords | None:
    tax_id_candidates: list[RealEstateRecords] = []

    if land.tax_id:
        estate_by_tax = await db.execute(select(RealEstateRecords).where(RealEstateRecords.tax_id == land.tax_id))
        tax_id_candidates = estate_by_tax.scalars().all()

    def score(candidate: RealEstateRecords) -> float:
        points = 0.0
        if land.cadastral_number and candidate.cadastral_number == land.cadastral_number:
            points += 0.55
        points += 0.25 * _location_similarity(land.location, candidate.address)
        points += 0.20 * _owner_similarity(land.owner_name, candidate.owner_name)
        if candidate.termination_date is not None:
            points -= 0.15
        return points

    # If identifiers match, keep the best candidate even with weak text similarity.
    if tax_id_candidates:
        return max(tax_id_candidates, key=score)

    candidates: list[RealEstateRecords] = []
    # Fallback search for cases where identifiers are incomplete in one registry.
    if land.cadastral_number or _is_meaningful_location(land.location):
        stmt = select(RealEstateRecords).where(
            or_(
                RealEstateRecords.cadastral_number == land.cadastral_number,
                func.similarity(land.location, RealEstateRecords.address) > 0.4,
            ),
        )
        estate_result = await db.execute(stmt)
        candidates = estate_result.scalars().all()

    if not candidates:
        return None

    best = max(candidates, key=score)
    return best if score(best) >= 0.30 else None


def _calc_loss(area_ha: Decimal | None, valuation: Decimal | None) -> Decimal:
    area = Decimal(area_ha or 0)
    valuation_value = Decimal(valuation or 0)
    return area * valuation_value * Decimal("0.03")


async def run_fuzzy_matching_audit(db: AsyncSession) -> tuple[list[Anomalies], bool]:

    await db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
    # Every audit run produces a fresh snapshot from current registers.
    await db.execute(delete(AuditLogs))
    await db.execute(delete(Anomalies))
    await db.flush()

    lands_result = await db.execute(select(LandRecords))
    lands = lands_result.scalars().all()

    anomalies_to_create: list[Anomalies] = []
    ai_candidates: list[AiAuditCandidate] = []
    quality_penalties: list[int] = []
    quality_notes: list[str] = []

    for land in lands:
        matched_estate = await _find_best_estate_match(db, land)
        trigger_reason: str | None = None
        zone = AnomalyZone.GREEN
        loss = Decimal("0.00")
        data_penalty, data_issues = _compute_data_quality_penalty(land)

        if not land.tax_id:
            trigger_reason = "Missing tax id in land register record."
            zone = AnomalyZone.RED
        elif not matched_estate:
            trigger_reason = "No matching real estate record by tax id/fuzzy criteria."
            zone = AnomalyZone.RED
            loss = _calc_loss(land.area_ha, land.valuation)
        else:
            matched_reasons: list[str] = []
            owner_similarity = _owner_similarity(land.owner_name, matched_estate.owner_name)
            if _is_unknown_owner(land.owner_name) or _is_unknown_owner(matched_estate.owner_name):
                matched_reasons.append("Owner name missing in one of the matched records.")
            elif owner_similarity < 0.72:
                matched_reasons.append(
                    "Owner names differ between matched records "
                    f"(similarity={owner_similarity:.2f})."
                )

            if land.cadastral_number and matched_estate.cadastral_number and land.cadastral_number != matched_estate.cadastral_number:
                matched_reasons.append("Cadastral numbers differ between matched records.")

            if _is_meaningful_location(land.location) and _is_meaningful_location(matched_estate.address):
                location_similarity = _location_similarity(land.location, matched_estate.address)
                if location_similarity < 0.45:
                    matched_reasons.append(f"Address/location mismatch (similarity={location_similarity:.2f}).")

            land_area_sqm = Decimal(land.area_ha or 0) * Decimal("10000")
            estate_area_sqm = Decimal(matched_estate.total_area_sqm or 0)
            if land_area_sqm > 0 and estate_area_sqm > 0:
                area_delta = abs(land_area_sqm - estate_area_sqm) / max(land_area_sqm, estate_area_sqm)
                if area_delta > Decimal("0.35"):
                    matched_reasons.append(f"Area mismatch between registries ({int(area_delta * 100)}% delta).")

            land_share = _normalize_share(land.ownership_share)
            estate_share = _normalize_share(matched_estate.ownership_share)
            if land_share and estate_share and land_share != estate_share:
                matched_reasons.append("Ownership share differs between matched records.")

            if matched_estate.termination_date is not None:
                matched_reasons.append(
                    f"Real estate rights are marked as terminated ({matched_estate.termination_date.isoformat()})."
                )

            if matched_reasons:
                trigger_reason = " ".join(matched_reasons)
                zone = AnomalyZone.GREEN

        if data_issues:
            data_reason = f"Data quality flags: {', '.join(data_issues)}."
            if trigger_reason:
                trigger_reason = f"{trigger_reason} {data_reason}"
            else:
                trigger_reason = data_reason
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
        quality_penalties.append(data_penalty)
        quality_notes.append(", ".join(data_issues) if data_issues else "")

        ai_candidates.append(
            AiAuditCandidate(
                zone=zone.value,
                tax_id=land.tax_id,
                purpose=land.purpose,
                ownership_type=land.ownership_type,
                owner_name_known=not _is_unknown_owner(land.owner_name),
                location=land.location,
                potential_loss_uah=float(loss),
            )
        )

    ai_result = await enrich_candidates_with_ai(ai_candidates, batch_size=5)
    for anomaly, profile, penalty, note in zip(anomalies_to_create, ai_result.profiles, quality_penalties, quality_notes):
        heuristic_summary = anomaly.ai_summary
        anomaly.risk_score = min(100, profile.risk_score + penalty)
        anomaly.ai_summary = f"{profile.ai_summary} Signals: {heuristic_summary}" if heuristic_summary else profile.ai_summary
        if note:
            anomaly.ai_summary = f"{anomaly.ai_summary} Data quality: {note}. +{penalty}% risk."
        anomaly.ai_decision_confidence = max(35, min(92, int(profile.decision_confidence)))

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
