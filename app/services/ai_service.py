from __future__ import annotations

import json
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.core.config import settings
from app.schemas.ai_schemas import AiAnomalyProfile, AiAuditCandidate

DEFAULT_BATCH_SIZE = 5


@dataclass(slots=True)
class AiBatchResult:
    profiles: list[AiAnomalyProfile]
    used_remote_ai: bool


def _local_profile(candidate: AiAuditCandidate) -> AiAnomalyProfile:
    purpose = (candidate.purpose or "").lower()
    ownership = (candidate.ownership_type or "").lower()

    if candidate.zone == "RED":
        risk_score = 80
        reason = "High risk: record was not matched across registries"
        confidence = 75
    elif "комунал" in ownership:
        risk_score = 45
        reason = "Potential community investment case"
        confidence = 65
    elif "комерц" in purpose:
        risk_score = 60
        reason = "Commercial purpose needs additional manual review"
        confidence = 70
    else:
        risk_score = 35
        reason = "Needs manual validation"
        confidence = 55

    return AiAnomalyProfile(
        risk_score=risk_score,
        ai_summary=reason,
        decision_confidence=confidence,
    )


def _apply_boost(candidate: AiAuditCandidate) -> int:
    boost = 0

    if candidate.zone == "RED":
        boost += 10

    if not candidate.tax_id:
        boost += 15

    if candidate.potential_loss_uah and candidate.potential_loss_uah > 100000:
        boost += 10

    purpose = (candidate.purpose or "").lower()
    if "комерц" in purpose or "komerc" in purpose:
        boost += 10

    return boost


def _adjust_confidence(candidate: AiAuditCandidate, base_confidence: int) -> int:
    confidence = base_confidence

    if not candidate.tax_id:
        confidence -= 10

    if not candidate.location:
        confidence -= 10

    if not candidate.purpose:
        confidence -= 10

    if candidate.purpose and candidate.ownership_type:
        confidence += 5

    if candidate.zone == "RED" and candidate.potential_loss_uah is not None:
        confidence += 5

    return max(0, min(100, confidence))


def _postprocess_profile(candidate: AiAuditCandidate, profile: AiAnomalyProfile) -> AiAnomalyProfile:
    boosted_risk = min(100, profile.risk_score + _apply_boost(candidate))
    adjusted_confidence = _adjust_confidence(candidate, profile.decision_confidence)

    summary = (profile.ai_summary or "").strip()
    if not summary:
        summary = "Insufficient data for conclusion."

    return AiAnomalyProfile(
        risk_score=boosted_risk,
        ai_summary=summary[:200],
        decision_confidence=adjusted_confidence,
    )


async def _request_profiles_from_openai(batch: list[AiAuditCandidate]) -> list[AiAnomalyProfile]:
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    prompt = (
        "You are an auditor for land and property registries. "
        "For each input item, return JSON object: "
        "{\"profiles\": [{\"risk_score\": int 0..100, \"ai_summary\": short string, "
        "\"decision_confidence\": int 0..100}]}. "
        "The profiles list must have the same length and order as input. "
        "Do not add any text outside JSON.\n\n"
        f"Input data: {json.dumps([item.model_dump() for item in batch], ensure_ascii=False)}"
    )

    completion = await client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
    )

    content = completion.choices[0].message.content or "{}"
    payload = json.loads(content)
    raw_profiles = payload.get("profiles", payload)

    if not isinstance(raw_profiles, list):
        raise ValueError("OpenAI response does not contain a list")

    profiles = [AiAnomalyProfile.model_validate(item) for item in raw_profiles]
    if len(profiles) != len(batch):
        raise ValueError("OpenAI response size mismatch")

    return profiles


async def enrich_candidates_with_ai(
    candidates: list[AiAuditCandidate],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> AiBatchResult:
    if not candidates:
        return AiBatchResult(profiles=[], used_remote_ai=False)

    # Do not fail the whole audit flow if external AI is unavailable.
    remote_ai_enabled = bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.strip())
    used_remote_ai = False
    profiles: list[AiAnomalyProfile] = []

    effective_batch_size = batch_size if batch_size > 0 else DEFAULT_BATCH_SIZE

    for start in range(0, len(candidates), effective_batch_size):
        batch = candidates[start : start + effective_batch_size]

        if remote_ai_enabled:
            try:
                batch_profiles = await _request_profiles_from_openai(batch)
                used_remote_ai = True
            except Exception:
                batch_profiles = [_local_profile(item) for item in batch]
        else:
            batch_profiles = [_local_profile(item) for item in batch]

        profiles.extend(_postprocess_profile(item, profile) for item, profile in zip(batch, batch_profiles))

    return AiBatchResult(profiles=profiles, used_remote_ai=used_remote_ai)



