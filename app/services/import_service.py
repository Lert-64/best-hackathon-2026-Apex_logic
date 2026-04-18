from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

import pandas as pd
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_model import Anomalies
from app.models.audit_log_model import AuditLogs
from app.models.land_model import LandRecords
from app.models.real_estate_model import RealEstateRecords

LAND_REQUIRED_COLUMNS = {
    "cadastral_number",
    "koatuu",
    "ownership_type",
    "purpose",
    "location",
    "area_ha",
    "valuation",
    "owner_name",
    "ownership_share",
    "reg_date",
    "record_number",
    "reg_authority",
    "doc_type",
}

ESTATE_REQUIRED_COLUMNS = {
    "tax_id",
    "owner_name",
    "object_type",
    "address",
    "total_area_sqm",
}


def _none_if_nan(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if pd.isna(value):
        return None
    return value


def _to_str(value: Any, field: str, required: bool = False) -> str | None:
    value = _none_if_nan(value)
    if value is None:
        if required:
            raise ValueError(f"Missing required value for '{field}'")
        return None
    text = str(value).strip()
    if required and not text:
        raise ValueError(f"Missing required value for '{field}'")
    return text or None


def _to_decimal(value: Any, field: str, required: bool = False) -> Decimal | None:
    value = _none_if_nan(value)
    if value is None:
        if required:
            raise ValueError(f"Missing required numeric value for '{field}'")
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for '{field}': {value}") from exc


def _to_date(value: Any, field: str, required: bool = False) -> date | None:
    value = _none_if_nan(value)
    if value is None:
        if required:
            raise ValueError(f"Missing required date value for '{field}'")
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Invalid date value for '{field}': {value}")
    return parsed.date()


async def _read_table(file: UploadFile) -> pd.DataFrame:
    filename = (file.filename or "").lower()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File '{file.filename}' is empty")

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(BytesIO(content))
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(BytesIO(content))
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format for '{file.filename}'. Use CSV or XLSX",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse '{file.filename}': {exc}",
        ) from exc

    if df.empty:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File '{file.filename}' has no rows")

    # Keep column names stable despite whitespace differences in source files.
    df.columns = [str(col).strip() for col in df.columns]
    return df


def _ensure_columns(df: pd.DataFrame, required: set[str], filename: str | None) -> None:
    missing = sorted(required.difference(df.columns))
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing columns in '{filename}': {', '.join(missing)}",
        )


async def import_registers(
    db: AsyncSession,
    land_file: UploadFile,
    real_estate_file: UploadFile,
) -> dict[str, int]:
    land_df = await _read_table(land_file)
    estate_df = await _read_table(real_estate_file)

    _ensure_columns(land_df, LAND_REQUIRED_COLUMNS, land_file.filename)
    _ensure_columns(estate_df, ESTATE_REQUIRED_COLUMNS, real_estate_file.filename)

    try:
        land_records: list[LandRecords] = []
        for row in land_df.to_dict(orient="records"):
            land_records.append(
                LandRecords(
                    cadastral_number=_to_str(row.get("cadastral_number"), "cadastral_number", required=True),
                    koatuu=_to_str(row.get("koatuu"), "koatuu", required=True),
                    ownership_type=_to_str(row.get("ownership_type"), "ownership_type", required=True),
                    purpose=_to_str(row.get("purpose"), "purpose", required=True),
                    location=_to_str(row.get("location"), "location", required=True),
                    agri_type=_to_str(row.get("agri_type"), "agri_type"),
                    area_ha=_to_decimal(row.get("area_ha"), "area_ha", required=True),
                    valuation=_to_decimal(row.get("valuation"), "valuation", required=True),
                    tax_id=_to_str(row.get("tax_id"), "tax_id"),
                    owner_name=_to_str(row.get("owner_name"), "owner_name", required=True),
                    ownership_share=_to_str(row.get("ownership_share"), "ownership_share", required=True),
                    reg_date=_to_date(row.get("reg_date"), "reg_date", required=True),
                    record_number=_to_str(row.get("record_number"), "record_number", required=True),
                    reg_authority=_to_str(row.get("reg_authority"), "reg_authority", required=True),
                    doc_type=_to_str(row.get("doc_type"), "doc_type", required=True),
                    doc_subtype=_to_str(row.get("doc_subtype"), "doc_subtype"),
                )
            )

        estate_records: list[RealEstateRecords] = []
        for row in estate_df.to_dict(orient="records"):
            estate_records.append(
                RealEstateRecords(
                    tax_id=_to_str(row.get("tax_id"), "tax_id", required=True),
                    owner_name=_to_str(row.get("owner_name"), "owner_name", required=True),
                    object_type=_to_str(row.get("object_type"), "object_type", required=True),
                    address=_to_str(row.get("address"), "address", required=True),
                    cadastral_number=_to_str(row.get("cadastral_number"), "cadastral_number"),
                    reg_date=_to_date(row.get("reg_date"), "reg_date"),
                    termination_date=_to_date(row.get("termination_date"), "termination_date"),
                    total_area_sqm=_to_decimal(row.get("total_area_sqm"), "total_area_sqm", required=True),
                    joint_ownership_type=_to_str(row.get("joint_ownership_type"), "joint_ownership_type"),
                    ownership_share=_to_str(row.get("ownership_share"), "ownership_share"),
                )
            )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    async with db.begin():
        # Import acts as a new audit cycle, so older matches and logs are reset.
        await db.execute(delete(AuditLogs))
        await db.execute(delete(Anomalies))
        await db.execute(delete(LandRecords))
        await db.execute(delete(RealEstateRecords))

        db.add_all(land_records)
        db.add_all(estate_records)

    return {
        "land_rows": len(land_records),
        "real_estate_rows": len(estate_records),
    }

