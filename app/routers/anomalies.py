from pathlib import Path
import re
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, or_, select

from app.backend.dependencies import db_dep, require_role
from app.core.config import settings
from app.models.anomaly_model import Anomalies, AnomalyStatus, AnomalyZone
from app.models.audit_log_model import AuditLogs
from app.models.land_model import LandRecords
from app.models.real_estate_model import RealEstateRecords
from app.models.user_model import UserRole
from app.schemas.anomaly_schemas import (
    AdminDecisionSubmit,
    AnomalyResponse,
    AnomalyStatsResponse,
    InspectorReportSubmit,
    TakeTaskResponse,
)

router = APIRouter(prefix="/api/anomalies", tags=["Anomalies"])

templates = Jinja2Templates(directory="app/templates")

MEDIA_ROOT = Path(settings.MEDIA_ROOT)
VOLUNTEER_UPLOAD_DIR = MEDIA_ROOT / "volunteer_reports"


async def _to_response(anomaly: Anomalies, db: db_dep) -> AnomalyResponse:
    placeholder_values = {
        "unknown",
        "unknown_owner",
        "невідомо",
        "не відомо",
        "none",
        "null",
        "n/a",
    }

    land_stmt = select(LandRecords.owner_name, LandRecords.cadastral_number, LandRecords.location).where(
        LandRecords.lid == anomaly.land_id
    )
    land_result = await db.execute(land_stmt)
    land_owner_name, land_cadastral_number, land_location = land_result.one_or_none() or (None, "", None)

    estate_owner_name = None
    estate_cadastral_number = None
    estate_address = None
    if anomaly.real_estate_id:
        estate_stmt = select(
            RealEstateRecords.owner_name,
            RealEstateRecords.cadastral_number,
            RealEstateRecords.address,
        ).where(RealEstateRecords.lid == anomaly.real_estate_id)
        estate_result = await db.execute(estate_stmt)
        estate_owner_name, estate_cadastral_number, estate_address = estate_result.one_or_none() or (None, None, None)

    def _clean_owner(value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.lower() in placeholder_values:
            return None
        return normalized

    def _clean_location(value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.lower() in placeholder_values:
            return None
        return normalized

    owner_name = _clean_owner(land_owner_name) or _clean_owner(estate_owner_name)
    cadastral_number = land_cadastral_number or estate_cadastral_number or ""
    location = _clean_location(land_location) or _clean_location(estate_address)

    # Some legacy anomalies may not have real_estate_id populated; fallback by tax_id.
    if (not owner_name or not cadastral_number or not location) and anomaly.tax_id:
        estate_by_tax_stmt = select(
            RealEstateRecords.owner_name,
            RealEstateRecords.cadastral_number,
            RealEstateRecords.address,
        ).where(RealEstateRecords.tax_id == anomaly.tax_id)
        estate_by_tax_result = await db.execute(estate_by_tax_stmt)
        for tax_owner_name, tax_cadastral_number, tax_address in estate_by_tax_result.all():
            owner_name = owner_name or _clean_owner(tax_owner_name)
            cadastral_number = cadastral_number or tax_cadastral_number or ""
            location = location or _clean_location(tax_address)
            if owner_name and cadastral_number and location:
                break

    # Tax identifiers are often missing in uploaded registries; fallback by cadastral number shape.
    if (not owner_name or not location) and cadastral_number:
        cadastral_digits = re.sub(r"\D", "", cadastral_number)
        if cadastral_digits:
            estate_by_cadastral_stmt = select(
                RealEstateRecords.owner_name,
                RealEstateRecords.cadastral_number,
                RealEstateRecords.address,
            ).where(
                func.regexp_replace(RealEstateRecords.cadastral_number, r"\D", "", "g") == cadastral_digits
            )
            estate_by_cadastral_result = await db.execute(estate_by_cadastral_stmt)
            for cad_owner_name, cad_cadastral_number, cad_address in estate_by_cadastral_result.all():
                owner_name = owner_name or _clean_owner(cad_owner_name)
                cadastral_number = cadastral_number or cad_cadastral_number or ""
                location = location or _clean_location(cad_address)
                if owner_name and location:
                    break

    volunteer_photo_url = None
    if anomaly.volunteer_photo_path:
        volunteer_photo_url = f"/media/{anomaly.volunteer_photo_path}"

    return AnomalyResponse(
        id=anomaly.lid,
        zone=anomaly.zone,
        tax_id=anomaly.tax_id,
        owner_name=owner_name,
        cadastral_number=cadastral_number,
        location=location,
        potential_loss_uah=float(anomaly.potential_loss_uah) if anomaly.potential_loss_uah is not None else None,
        risk_score=anomaly.risk_score,
        ai_summary=anomaly.ai_summary,
        ai_decision_confidence=anomaly.ai_decision_confidence,
        status=anomaly.status,
        volunteer_id=anomaly.volunteer_id,
        volunteer_photo_url=volunteer_photo_url,
        volunteer_comment=anomaly.volunteer_comment,
        inspector_id=anomaly.inspector_id,
        inspector_comment=anomaly.inspector_comment,
        created_at=anomaly.created_at,
    )


def _audit_log(anomaly_id: UUID, reason: str, action: str, user_id: UUID | None) -> AuditLogs:
    return AuditLogs(
        anomaly_id=anomaly_id,
        action=action,
        reason=reason,
        user_id=user_id,
    )


async def _parse_inspector_report_payload(request: Request) -> InspectorReportSubmit:
    content_type = (request.headers.get("content-type") or "").lower()
    try:
        if "application/json" in content_type:
            payload = await request.json()
        else:
            form = await request.form()
            payload = {
                "is_confirmed": form.get("is_confirmed"),
                "inspector_comment": form.get("inspector_comment"),
            }
        return InspectorReportSubmit.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc


@router.get("", response_model=list[AnomalyResponse])
async def list_anomalies(
    db: db_dep,
    _=Depends(require_role(UserRole.ADMIN)),
):
    stmt = select(Anomalies).order_by(Anomalies.created_at.desc())
    result = await db.execute(stmt)
    anomalies = result.scalars().all()
    return [await _to_response(anomaly, db) for anomaly in anomalies]


@router.get("/stats", response_model=AnomalyStatsResponse)
async def get_anomaly_stats(
    db: db_dep,
    _=Depends(require_role(UserRole.ADMIN)),
):
    result = await db.execute(select(Anomalies.status))
    statuses = result.scalars().all()

    return AnomalyStatsResponse(
        total=len(statuses),
        pending_admin=sum(1 for status in statuses if status == AnomalyStatus.PENDING_ADMIN),
        new=sum(1 for status in statuses if status == AnomalyStatus.NEW),
        in_work=sum(1 for status in statuses if status == AnomalyStatus.IN_WORK),
        pending_inspector=sum(1 for status in statuses if status == AnomalyStatus.PENDING_INSPECTOR),
        resolved=sum(1 for status in statuses if status == AnomalyStatus.RESOLVED),
        dismissed=sum(1 for status in statuses if status == AnomalyStatus.DISMISSED),
    )


@router.get("/pending-admin", response_model=list[AnomalyResponse])
async def list_pending_admin_review(
    db: db_dep,
    _=Depends(require_role(UserRole.ADMIN)),
):
    stmt = (
        select(Anomalies)
        .where(Anomalies.status == AnomalyStatus.PENDING_ADMIN)
        .order_by(Anomalies.created_at.asc())
    )
    result = await db.execute(stmt)
    anomalies = result.scalars().all()
    return [await _to_response(anomaly, db) for anomaly in anomalies]


@router.post("/{anomaly_id}/admin-decision", response_model=AnomalyResponse)
async def submit_admin_decision(
    anomaly_id: UUID,
    payload: AdminDecisionSubmit,
    db: db_dep,
    current_user=Depends(require_role(UserRole.ADMIN)),
):
    stmt = select(Anomalies).where(Anomalies.lid == anomaly_id).with_for_update()
    result = await db.execute(stmt)
    anomaly = result.scalar_one_or_none()

    if anomaly is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly not found")

    if anomaly.status != AnomalyStatus.PENDING_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Anomaly is not waiting for admin review",
        )

    if not payload.is_confirmed and not payload.reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="reason is required when anomaly is rejected",
        )

    anomaly.status = AnomalyStatus.NEW if payload.is_confirmed else AnomalyStatus.DISMISSED
    reason = payload.reason or "Approved for volunteer pool"
    action = "ADMIN_APPROVED" if payload.is_confirmed else "ADMIN_REJECTED"
    db.add(_audit_log(anomaly.lid, reason, action, current_user.id))
    await db.commit()

    return await _to_response(anomaly, db)


@router.get("/pool", response_model=list[AnomalyResponse])
async def list_pool(
    db: db_dep,
    _=Depends(require_role(UserRole.VOLUNTEER)),
):
    stmt = (
        select(Anomalies)
        .where(
            Anomalies.zone == AnomalyZone.RED,
            or_(Anomalies.status == AnomalyStatus.NEW, Anomalies.status == AnomalyStatus.PENDING_ADMIN),
        )
        .order_by(Anomalies.created_at.asc())
    )
    result = await db.execute(stmt)
    anomalies = result.scalars().all()
    return [await _to_response(anomaly, db) for anomaly in anomalies]


@router.get("/pool/html", response_class=HTMLResponse)
async def list_pool_html(request: Request, db: db_dep, _=Depends(require_role(UserRole.VOLUNTEER))):
    stmt = (
        select(Anomalies)
        .where(
            Anomalies.zone == AnomalyZone.RED,
            or_(Anomalies.status == AnomalyStatus.NEW, Anomalies.status == AnomalyStatus.PENDING_ADMIN),
        )
        .order_by(Anomalies.created_at.asc())
    )
    result = await db.execute(stmt)
    anomalies = result.scalars().all()
    responses = [await _to_response(anomaly, db) for anomaly in anomalies]
    return templates.TemplateResponse(
        request=request,
        name="pool_list.html",
        context={"request": request, "anomalies": responses},
    )


@router.get("/pending-validation", response_model=list[AnomalyResponse])
async def list_pending_validation(
    db: db_dep,
    _=Depends(require_role(UserRole.INSPECTOR)),
):
    stmt = (
        select(Anomalies)
        .where(Anomalies.status == AnomalyStatus.PENDING_INSPECTOR)
        .order_by(Anomalies.created_at.asc())
    )
    result = await db.execute(stmt)
    anomalies = result.scalars().all()
    return [await _to_response(anomaly, db) for anomaly in anomalies]


@router.get("/pending-validation/html", response_class=HTMLResponse)
async def list_pending_validation_html(request: Request, db: db_dep, _=Depends(require_role(UserRole.INSPECTOR))):
    stmt = (
        select(Anomalies)
        .where(Anomalies.status == AnomalyStatus.PENDING_INSPECTOR)
        .order_by(Anomalies.created_at.asc())
    )
    result = await db.execute(stmt)
    anomalies = result.scalars().all()
    responses = [await _to_response(anomaly, db) for anomaly in anomalies]
    return templates.TemplateResponse(
        request=request,
        name="pending_validation_list.html",
        context={"request": request, "anomalies": responses},
    )


@router.post("/{anomaly_id}/take", response_model=TakeTaskResponse)
async def take_task(
    anomaly_id: UUID,
    db: db_dep,
    current_user=Depends(require_role(UserRole.VOLUNTEER)),
):
    stmt = select(Anomalies).where(Anomalies.lid == anomaly_id).with_for_update()
    result = await db.execute(stmt)
    anomaly = result.scalar_one_or_none()

    if anomaly is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly not found")

    # Idempotent pickup: stale cards can retry while task is already assigned to the same volunteer.
    if anomaly.status == AnomalyStatus.IN_WORK and anomaly.volunteer_id == current_user.id:
        return TakeTaskResponse(anomaly_id=anomaly.lid, status=anomaly.status)

    if anomaly.status not in {AnomalyStatus.NEW, AnomalyStatus.PENDING_ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task is not available in the pool",
        )

    if anomaly.zone != AnomalyZone.RED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only RED anomalies are available for volunteer field work",
        )

    anomaly.status = AnomalyStatus.IN_WORK
    anomaly.volunteer_id = current_user.id
    db.add(_audit_log(anomaly.lid, "Task taken by volunteer", "TAKEN", current_user.id))
    await db.commit()

    return TakeTaskResponse(anomaly_id=anomaly.lid, status=anomaly.status)


@router.post("/{anomaly_id}/volunteer-report", response_model=AnomalyResponse)
async def submit_volunteer_report(
    anomaly_id: UUID,
    db: db_dep,
    photo: UploadFile = File(...),
    comment: str = Form(...),
    current_user=Depends(require_role(UserRole.VOLUNTEER)),
):
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only image uploads are allowed")

    file_ext = Path(photo.filename or "").suffix or ".jpg"
    file_name = f"{anomaly_id}_{uuid4().hex}{file_ext}"

    VOLUNTEER_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = VOLUNTEER_UPLOAD_DIR / file_name

    contents = await photo.read()
    with file_path.open("wb") as out_file:
        out_file.write(contents)

    relative_path = f"volunteer_reports/{file_name}"

    stmt = select(Anomalies).where(Anomalies.lid == anomaly_id).with_for_update()
    result = await db.execute(stmt)
    anomaly = result.scalar_one_or_none()

    if anomaly is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly not found")

    if anomaly.status != AnomalyStatus.IN_WORK or anomaly.volunteer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only the assigned volunteer can submit a report for an in-work task",
        )

    anomaly.volunteer_comment = comment
    anomaly.volunteer_photo_path = relative_path
    anomaly.status = AnomalyStatus.PENDING_INSPECTOR

    db.add(_audit_log(anomaly.lid, "Volunteer report submitted", "VOLUNTEER_SUBMIT", current_user.id))
    await db.commit()

    return await _to_response(anomaly, db)


@router.post("/{anomaly_id}/report", response_model=AnomalyResponse)
async def submit_inspector_decision(
    anomaly_id: UUID,
    request: Request,
    db: db_dep,
    current_user=Depends(require_role(UserRole.INSPECTOR)),
):
    payload = await _parse_inspector_report_payload(request)

    stmt = select(Anomalies).where(Anomalies.lid == anomaly_id).with_for_update()
    result = await db.execute(stmt)
    anomaly = result.scalar_one_or_none()

    if anomaly is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly not found")

    if anomaly.status != AnomalyStatus.PENDING_INSPECTOR:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Anomaly is not waiting for inspector validation",
        )

    if not payload.is_confirmed and not payload.inspector_comment:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="inspector_comment is required when report is rejected",
        )

    anomaly.inspector_id = current_user.id
    anomaly.inspector_comment = payload.inspector_comment
    anomaly.status = AnomalyStatus.RESOLVED if payload.is_confirmed else AnomalyStatus.DISMISSED

    action = "INSPECTOR_CONFIRMED" if payload.is_confirmed else "INSPECTOR_REJECTED"
    reason = payload.inspector_comment or "Inspector approved volunteer report"
    db.add(_audit_log(anomaly.lid, reason, action, current_user.id))
    await db.commit()

    # HTMX inspector flow expects HTML to re-render the queue container.
    if request.headers.get("HX-Request") == "true":
        stmt = (
            select(Anomalies)
            .where(Anomalies.status == AnomalyStatus.PENDING_INSPECTOR)
            .order_by(Anomalies.created_at.asc())
        )
        result = await db.execute(stmt)
        anomalies = result.scalars().all()
        responses = [await _to_response(item, db) for item in anomalies]
        return templates.TemplateResponse(
            request=request,
            name="pending_validation_list.html",
            context={"request": request, "anomalies": responses},
        )

    return await _to_response(anomaly, db)


