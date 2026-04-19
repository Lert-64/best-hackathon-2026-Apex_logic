from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re
from typing import Any, cast

import pandas as pd
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_model import Anomalies
from app.models.audit_log_model import AuditLogs
from app.models.land_model import LandRecords
from app.models.real_estate_model import RealEstateRecords

LAND_REQUIRED_COLUMNS = {
    "tax_id",
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

MISSING_OWNERSHIP_SHARE_FALLBACK = "UNKNOWN"
MISSING_OWNER_NAME_FALLBACK = "UNKNOWN_OWNER"
MISSING_RECORD_NUMBER_PREFIX = "AUTO-REC"
MISSING_TEXT_FALLBACK = "UNKNOWN"
MISSING_REG_DATE_FALLBACK = date(1900, 1, 1)
UNKNOWN_OWNER_VALUES = {"", "unknown", "unknown_owner", "невідомо", "не відомо", "none", "null", "n/a"}

LAND_COLUMN_ALIASES = {
    "cadastral_number": "cadastral_number",
    "cadastral_no": "cadastral_number",
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
    "kod": "tax_id",
    "kod_edrpou": "tax_id",
    "identyfikator": "tax_id",
    "identyfikatsiinyi_kod": "tax_id",
    "identifikatsiyniy_kod": "tax_id",
    "kod_platnyka_podatkiv": "tax_id",
    "rnokpp_edrpou": "tax_id",
    "ipn": "tax_id",
    "edrpou": "tax_id",
    "yedrpou": "tax_id",
    "yedrpou_zemlekorystuvacha": "tax_id",
    "yedrpou_zemlekorystuvach": "tax_id",
    "rnokpp": "tax_id",
    "owner_name": "owner_name",
    "owner": "owner_name",
    "owner_full_name": "owner_name",
    "vlasnyk": "owner_name",
    "nazva_vlasnyka": "owner_name",
    "pib": "owner_name",
    "p_i_b": "owner_name",
    "prizvyshche_im_ya_po_batkovi": "owner_name",
    "prizvyshche_im_ia_po_batkovi": "owner_name",
    "prizvyshche_imya_po_batkovi": "owner_name",
    "owner_last_name": "owner_last_name",
    "last_name": "owner_last_name",
    "surname": "owner_last_name",
    "prizvyshche": "owner_last_name",
    "owner_first_name": "owner_first_name",
    "first_name": "owner_first_name",
    "name": "owner_first_name",
    "im_ya": "owner_first_name",
    "imya": "owner_first_name",
    "owner_middle_name": "owner_middle_name",
    "middle_name": "owner_middle_name",
    "patronymic": "owner_middle_name",
    "po_batkovi": "owner_middle_name",
    "zemlekorystuvach": "owner_name",
    "ownership_share": "ownership_share",
    "chastka_vlasnosti": "ownership_share",
    "chastka_volodinnya": "ownership_share",
    "reg_date": "reg_date",
    "data_reiestracii": "reg_date",
    "data_reyestratsii": "reg_date",
    "data_reyestratsiyi": "reg_date",
    "data_reiestratsiyi": "reg_date",
    "data_derzhavnoyi_reyestratsiyi_prava": "reg_date",
    "data_derzhavnoyi_reyestratsiyi_prava_vlasnosti": "reg_date",
    "record_number": "record_number",
    "nomer_zapysu": "record_number",
    "nomer_zapysu_pro_pravo": "record_number",
    "nomer_zapysu_pro_prava": "record_number",
    "nomer_zapysu_pro_pravo_vlasnosti": "record_number",
    "nomer_zapysu_pro_prava_vlasnosti": "record_number",
    "reg_authority": "reg_authority",
    "organ_reiestracii": "reg_authority",
    "organ_reyestratsii": "reg_authority",
    "orhan_reyestratsii": "reg_authority",
    "orhan_reiestracii": "reg_authority",
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
    "kod": "tax_id",
    "kod_edrpou": "tax_id",
    "identyfikator": "tax_id",
    "identyfikatsiinyi_kod": "tax_id",
    "identifikatsiyniy_kod": "tax_id",
    "kod_platnyka_podatkiv": "tax_id",
    "rnokpp_edrpou": "tax_id",
    "ipn": "tax_id",
    "edrpou": "tax_id",
    "yedrpou": "tax_id",
    "rnokpp": "tax_id",
    "podatkovyi_nomer_pp": "tax_id",
    "podatkovyi_nomer": "tax_id",
    "owner_name": "owner_name",
    "owner": "owner_name",
    "owner_full_name": "owner_name",
    "vlasnyk": "owner_name",
    "nazva_platnyka": "owner_name",
    "nazva_vlasnyka": "owner_name",
    "pib": "owner_name",
    "p_i_b": "owner_name",
    "prizvyshche_im_ya_po_batkovi": "owner_name",
    "prizvyshche_im_ia_po_batkovi": "owner_name",
    "prizvyshche_imya_po_batkovi": "owner_name",
    "owner_last_name": "owner_last_name",
    "last_name": "owner_last_name",
    "surname": "owner_last_name",
    "prizvyshche": "owner_last_name",
    "owner_first_name": "owner_first_name",
    "first_name": "owner_first_name",
    "name": "owner_first_name",
    "im_ya": "owner_first_name",
    "imya": "owner_first_name",
    "owner_middle_name": "owner_middle_name",
    "middle_name": "owner_middle_name",
    "patronymic": "owner_middle_name",
    "po_batkovi": "owner_middle_name",
    "object_type": "object_type",
    "typ_obiekta": "object_type",
    "typ_obyekta": "object_type",
    "typ_ob_yekta": "object_type",
    "typ_ob_iekta": "object_type",
    "address": "address",
    "location": "address",
    "adresa": "address",
    "adres": "address",
    "adresa_obiekta": "address",
    "adresa_ob_yekta": "address",
    "adresa_ob_iekta": "address",
    "total_area_sqm": "total_area_sqm",
    "zahalna_ploshcha_kv_m": "total_area_sqm",
    "zahalna_ploshcha_kvm": "total_area_sqm",
    "zahalna_ploshcha": "total_area_sqm",
    "cadastral_number": "cadastral_number",
    "kadastrovyi_nomer": "cadastral_number",
    "reg_date": "reg_date",
    "data_reiestracii": "reg_date",
    "data_reyestratsii": "reg_date",
    "data_reyestratsiyi": "reg_date",
    "data_reiestratsiyi": "reg_date",
    "data_derzh_reyestr_prava_vlasn": "reg_date",
    "termination_date": "termination_date",
    "data_prypynennia": "termination_date",
    "data_derzh_reyestr_pryp_prava_vlasn": "termination_date",
    "joint_ownership_type": "joint_ownership_type",
    "spilna_vlasnist_type": "joint_ownership_type",
    "vyd_spilnoyi_vlasnosti": "joint_ownership_type",
    "vyd_spil_noyi_vlasnosti": "joint_ownership_type",
    "ownership_share": "ownership_share",
    "chastka_vlasnosti": "ownership_share",
    "rozmir_chastky_u_pravi_spilnoyi_vlasnosti": "ownership_share",
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


def _to_tax_id(value: Any, required: bool = False) -> str | None:
    value = _none_if_nan(value)
    if value is None:
        if required:
            raise ValueError("Missing required value for 'tax_id'")
        return None

    text = str(value).strip().replace("\u00a0", "")
    if not text:
        if required:
            raise ValueError("Missing required value for 'tax_id'")
        return None

    lowered = text.lower()
    if lowered in {"#н/д", "#n/a", "n/a", "nan", "none", "null"}:
        if required:
            raise ValueError("Missing required value for 'tax_id'")
        return None

    compact = re.sub(r"\s+", "", text)

    # Handle values like 1,25E+09 and keep the full integer identifier.
    if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?", compact):
        numeric_text = compact.replace(",", ".")
        try:
            numeric_value = Decimal(numeric_text)
            if numeric_value == numeric_value.to_integral_value():
                return str(int(numeric_value))
        except InvalidOperation:
            pass

    if re.search(r"\d", compact):
        digits = re.sub(r"\D", "", compact)
        if digits:
            return digits

    if required:
        raise ValueError("Missing required value for 'tax_id'")
    return None


def _to_decimal(value: Any, field: str, required: bool = False) -> Decimal | None:
    value = _none_if_nan(value)
    if value is None:
        if required:
            raise ValueError(f"Missing required numeric value for '{field}'")
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        if not required:
            return None
        raise ValueError(f"Invalid numeric value for '{field}': {value}") from exc


def _to_date(value: Any, field: str, required: bool = False) -> date | None:
    value = _none_if_nan(value)
    if value is None:
        if required:
            raise ValueError(f"Missing required date value for '{field}'")
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        if not required:
            return None
        raise ValueError(f"Invalid date value for '{field}': {value}")
    return parsed.date()


def _inject_missing_columns(df: pd.DataFrame, expected_columns: set[str]) -> pd.DataFrame:
    for column in expected_columns:
        if column not in df.columns:
            df[column] = None
    return df


def _compose_owner_name_columns(df: pd.DataFrame) -> pd.DataFrame:
    part_columns = [column for column in ("owner_last_name", "owner_first_name", "owner_middle_name") if column in df.columns]
    has_owner_column = "owner_name" in df.columns
    if not part_columns and has_owner_column:
        return df

    if not has_owner_column:
        df["owner_name"] = None

    def _is_missing_owner(value: Any) -> bool:
        text = (_to_str(value, "owner_name", required=False) or "").strip().lower()
        return text in UNKNOWN_OWNER_VALUES

    def _join_owner_parts(row: pd.Series) -> str | None:
        parts: list[str] = []
        for column in ("owner_last_name", "owner_first_name", "owner_middle_name"):
            if column not in row.index:
                continue
            value = _to_str(row.get(column), column, required=False)
            if value:
                parts.append(value)
        return " ".join(parts) if parts else None

    if part_columns:
        composed_names = df.apply(_join_owner_parts, axis=1)
        for index, composed in composed_names.items():
            if composed and _is_missing_owner(df.at[index, "owner_name"]):
                df.at[index, "owner_name"] = composed

    return df


def _is_missing_owner_value(value: Any) -> bool:
    text = (_to_str(value, "owner_name", required=False) or "").strip().lower()
    return text in UNKNOWN_OWNER_VALUES


def _looks_like_owner_column(column_name: str) -> bool:
    normalized = _normalize_header(column_name)
    owner_markers = (
        "owner",
        "vlasnyk",
        "zemlekorystuvach",
        "prizvyshche",
        "imya",
        "im_ya",
        "po_batkovi",
        "pib",
        "nazva_vlasnyka",
        "nazva_platnyka",
    )
    return any(marker in normalized for marker in owner_markers)


def _resolve_owner_name(row: dict[str, Any]) -> str | None:
    explicit = _to_str(row.get("owner_name"), "owner_name", required=False)
    if explicit and not _is_missing_owner_value(explicit):
        return explicit

    split_parts = [
        _to_str(row.get("owner_last_name"), "owner_last_name", required=False),
        _to_str(row.get("owner_first_name"), "owner_first_name", required=False),
        _to_str(row.get("owner_middle_name"), "owner_middle_name", required=False),
    ]
    composed = " ".join(part for part in split_parts if part)
    if composed:
        return composed

    fallback_candidates: list[str] = []
    for key, value in row.items():
        if not _looks_like_owner_column(str(key)):
            continue
        candidate = _to_str(value, str(key), required=False)
        if not candidate or _is_missing_owner_value(candidate):
            continue
        fallback_candidates.append(candidate)

    if not fallback_candidates:
        return None

    # Prefer the most informative owner-like value when multiple columns exist.
    return max(fallback_candidates, key=lambda value: len(value.strip()))


def _read_csv_dataframe(content: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp1251", "utf-8"):
        try:
            parsed_any: Any = pd.read_csv(
                BytesIO(content),
                sep=None,
                engine="python",
                encoding=encoding,
                iterator=False,
                chunksize=None,
            )
            return cast(pd.DataFrame, parsed_any if isinstance(parsed_any, pd.DataFrame) else parsed_any.read())
        except Exception as exc:  # pragma: no cover - only exercised for non-matching encodings
            last_error = exc

    raise ValueError(last_error or "Unknown CSV parse error")


async def _read_table(file: UploadFile) -> pd.DataFrame:
    filename = (file.filename or "").lower()
    content: bytes = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File '{file.filename}' is empty")

    if not (filename.endswith(".csv") or filename.endswith(".xlsx") or filename.endswith(".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format for '{file.filename}'. Use CSV or XLSX",
        )

    try:
        if filename.endswith(".csv"):
            df = cast(pd.DataFrame, _read_csv_dataframe(content))
        else:
            parsed_any: Any = pd.read_excel(BytesIO(content))
            df = cast(pd.DataFrame, parsed_any if isinstance(parsed_any, pd.DataFrame) else parsed_any.read())
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
        available = ", ".join(sorted(str(column) for column in df.columns)[:30])
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

    land_df = _compose_owner_name_columns(land_df)
    estate_df = _compose_owner_name_columns(estate_df)

    # Estate files may come with address-like headers that heuristics map to "location".
    if "address" not in estate_df.columns and "location" in estate_df.columns:
        estate_df = estate_df.rename(columns={"location": "address"})

    _ensure_columns(land_df, LAND_REQUIRED_COLUMNS, land_file.filename)
    _ensure_columns(estate_df, ESTATE_REQUIRED_COLUMNS, real_estate_file.filename)

    try:
        land_records: list[LandRecords] = []
        for index, row in enumerate(land_df.to_dict(orient="records"), start=1):
            # Some source exports contain blank record numbers in individual rows.
            record_number = _to_str(row.get("record_number"), "record_number", required=False) or (
                f"{MISSING_RECORD_NUMBER_PREFIX}-{index:06d}"
            )
            land_records.append(
                LandRecords(
                    cadastral_number=(
                        _to_str(row.get("cadastral_number"), "cadastral_number") or f"AUTO-LAND-{record_number}-{index}"
                    ),
                    koatuu=_to_str(row.get("koatuu"), "koatuu") or MISSING_TEXT_FALLBACK,
                    ownership_type=_to_str(row.get("ownership_type"), "ownership_type") or MISSING_TEXT_FALLBACK,
                    purpose=_to_str(row.get("purpose"), "purpose") or MISSING_TEXT_FALLBACK,
                    location=_to_str(row.get("location"), "location") or MISSING_TEXT_FALLBACK,
                    agri_type=_to_str(row.get("agri_type"), "agri_type"),
                    area_ha=_to_decimal(row.get("area_ha"), "area_ha") or Decimal("0"),
                    valuation=_to_decimal(row.get("valuation"), "valuation") or Decimal("0"),
                    tax_id=_to_tax_id(row.get("tax_id"), required=False),
                    owner_name=_resolve_owner_name(row) or MISSING_OWNER_NAME_FALLBACK,
                    ownership_share=(
                        _to_str(row.get("ownership_share"), "ownership_share", required=False)
                        or MISSING_OWNERSHIP_SHARE_FALLBACK
                    ),
                    reg_date=_to_date(row.get("reg_date"), "reg_date", required=False) or MISSING_REG_DATE_FALLBACK,
                    record_number=record_number,
                    reg_authority=_to_str(row.get("reg_authority"), "reg_authority", required=False)
                    or MISSING_TEXT_FALLBACK,
                    doc_type=_to_str(row.get("doc_type"), "doc_type", required=False) or MISSING_TEXT_FALLBACK,
                    doc_subtype=_to_str(row.get("doc_subtype"), "doc_subtype"),
                )
            )

        estate_records: list[RealEstateRecords] = []
        for index, row in enumerate(estate_df.to_dict(orient="records"), start=1):
            estate_tax_id = _to_tax_id(row.get("tax_id"), required=False) or f"UNKNOWN-ESTATE-{index}"
            estate_records.append(
                RealEstateRecords(
                    tax_id=estate_tax_id,
                    owner_name=_resolve_owner_name(row) or MISSING_OWNER_NAME_FALLBACK,
                    object_type=_to_str(row.get("object_type"), "object_type", required=False) or MISSING_TEXT_FALLBACK,
                    address=_to_str(row.get("address"), "address", required=False) or MISSING_TEXT_FALLBACK,
                    cadastral_number=_to_str(row.get("cadastral_number"), "cadastral_number"),
                    reg_date=_to_date(row.get("reg_date"), "reg_date"),
                    termination_date=_to_date(row.get("termination_date"), "termination_date"),
                    total_area_sqm=_to_decimal(row.get("total_area_sqm"), "total_area_sqm", required=False)
                    or Decimal("0"),
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

