from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re
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

LAND_COLUMN_ALIASES = {
    "cadastral_number": "cadastral_number",
    "cadastral_no": "cadastral_number",
    "kadastrovyi_nomer": "cadastral_number",
    "kadastrovyi_nomer": "cadastral_number",
    "kadastralnyi_nomer": "cadastral_number",
    "kadastr_number": "cadastral_number",
    "koatuu": "koatuu",
    "koatyy": "koatuu",
    "ownership_type": "ownership_type",
    "forma_vlasnosti": "ownership_type",
    "purpose": "purpose",
    "cilove_pryznachennia": "purpose",
    "tsilove_pryznachennya": "purpose",
    "location": "location",
    "misceznahodzhennia": "location",
    "mistseznakhodzhennia": "location",
    "address": "location",
    "area_ha": "area_ha",
    "ploshcha_ha": "area_ha",
    "valuation": "valuation",
    "ngo": "valuation",
    "ocinka": "valuation",
    "otsinka": "valuation",
    "tax_id": "tax_id",
    "edrpou": "tax_id",
    "yedrpou": "tax_id",
    "rnokpp": "tax_id",
    "owner_name": "owner_name",
    "vlasnyk": "owner_name",
    "zemlekorystuvach": "owner_name",
    "ownership_share": "ownership_share",
    "chastka_vlasnosti": "ownership_share",
    "chastka_volodinnya": "ownership_share",
    "reg_date": "reg_date",
    "data_reiestracii": "reg_date",
    "data_reyestratsii": "reg_date",
    "data_reyestratsiyi": "reg_date",
    "data_reiestratsiyi": "reg_date",
    "record_number": "record_number",
    "nomer_zapysu": "record_number",
    "reg_authority": "reg_authority",
    "organ_reiestracii": "reg_authority",
    "organ_reyestratsii": "reg_authority",
    "orhan_reyestratsii": "reg_authority",
    "orhan_reiestracii": "reg_authority",
    "orhan_reyestratsiyi": "reg_authority",
    "orhan_reiestratsiyi": "reg_authority",
    "orhan_shcho_zdiisnyv_derzhavnu_reyestratsiyu_prava_vlasnosti": "reg_authority",
    "doc_type": "doc_type",
    "typ_dokumenta": "doc_type",
    "typ": "doc_type",
    "agri_type": "agri_type",
    "doc_subtype": "doc_subtype",
    "pidtyp": "doc_subtype",
}

ESTATE_COLUMN_ALIASES = {
    "tax_id": "tax_id",
    "edrpou": "tax_id",
    "yedrpou": "tax_id",
    "rnokpp": "tax_id",
    "owner_name": "owner_name",
    "vlasnyk": "owner_name",
    "object_type": "object_type",
    "typ_obiekta": "object_type",
    "typ_obyekta": "object_type",
    "address": "address",
    "adresa": "address",
    "adres": "address",
    "total_area_sqm": "total_area_sqm",
    "zahalna_ploshcha_kv_m": "total_area_sqm",
    "zahalna_ploshcha_kvm": "total_area_sqm",
    "cadastral_number": "cadastral_number",
    "kadastrovyi_nomer": "cadastral_number",
    "kadastrovyi_nomer": "cadastral_number",
    "reg_date": "reg_date",
    "data_reiestracii": "reg_date",
    "data_reyestratsii": "reg_date",
    "data_reyestratsiyi": "reg_date",
    "data_reiestratsiyi": "reg_date",
    "termination_date": "termination_date",
    "data_prypynennia": "termination_date",
    "joint_ownership_type": "joint_ownership_type",
    "spilna_vlasnist_type": "joint_ownership_type",
    "ownership_share": "ownership_share",
    "chastka_vlasnosti": "ownership_share",
}

CYRILLIC_MAP = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "h",
        "ґ": "g",
        "д": "d",
        "е": "e",
        "є": "ye",
        "ж": "zh",
        "з": "z",
        "и": "y",
        "і": "i",
        "ї": "yi",
        "й": "i",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "kh",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "shch",
        "ь": "",
        "ю": "yu",
        "я": "ya",
        "ъ": "",
        "ы": "y",
        "э": "e",
    }
)


def _normalize_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.translate(CYRILLIC_MAP)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _canonicalize_columns(df: pd.DataFrame, alias_map: dict[str, str]) -> pd.DataFrame:
    rename_map: dict[str, str] = {}
    used_targets: set[str] = set()

    for original in df.columns:
        normalized = _normalize_header(original)
        target = alias_map.get(normalized, normalized)
        if target in used_targets:
            continue
        rename_map[original] = target
        used_targets.add(target)

    return df.rename(columns=rename_map)


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
        available = ", ".join(sorted(df.columns)[:30])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Missing columns in '{filename}': {', '.join(missing)}. "
                f"Detected columns: {available}"
            ),
        )


async def import_registers(
    db: AsyncSession,
    land_file: UploadFile,
    real_estate_file: UploadFile,
) -> dict[str, int]:
    land_df = await _read_table(land_file)
    estate_df = await _read_table(real_estate_file)

    land_df = _canonicalize_columns(land_df, LAND_COLUMN_ALIASES)
    estate_df = _canonicalize_columns(estate_df, ESTATE_COLUMN_ALIASES)

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

    try:
        # Import acts as a new audit cycle, so older matches and logs are reset.
        await db.execute(delete(AuditLogs))
        await db.execute(delete(Anomalies))
        await db.execute(delete(LandRecords))
        await db.execute(delete(RealEstateRecords))

        db.add_all(land_records)
        db.add_all(estate_records)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {
        "land_rows": len(land_records),
        "real_estate_rows": len(estate_records),
    }

