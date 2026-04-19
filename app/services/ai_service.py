from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
from pydantic import BaseModel

from app.core.config import settings
from app.schemas.ai_schemas import AiAnomalyProfile, AiAuditCandidate

DEFAULT_BATCH_SIZE = 5


@dataclass(slots=True)
class AiBatchResult:
    profiles: list[AiAnomalyProfile]
    used_remote_ai: bool


class AiProfilesPayload(BaseModel):
    profiles: list[AiAnomalyProfile]


def _local_profile(candidate: AiAuditCandidate) -> AiAnomalyProfile:
    purpose = (candidate.purpose or "").lower()
    ownership = (candidate.ownership_type or "").lower()

    if candidate.zone == "RED":
        risk_score = 70
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
        boost += 6

    if not candidate.tax_id:
        boost += 8

    if candidate.potential_loss_uah and candidate.potential_loss_uah > 100000:
        boost += 8

    purpose = (candidate.purpose or "").lower()
    if "комерц" in purpose or "komerc" in purpose:
        boost += 6

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

    if candidate.owner_name_known is False:
        confidence -= 18

    if candidate.zone == "RED" and candidate.potential_loss_uah is not None:
        confidence += 5

    return max(0, min(100, confidence))


def _evidence_confidence(candidate: AiAuditCandidate) -> int:
    evidence = 45
    if candidate.tax_id:
        evidence += 8
    if candidate.location:
        evidence += 7
    if candidate.purpose:
        evidence += 5
    if candidate.ownership_type:
        evidence += 5
    if candidate.owner_name_known is False:
        evidence -= 12

    loss = candidate.potential_loss_uah or 0
    if loss > 300000:
        evidence += 10
    elif loss > 100000:
        evidence += 7
    elif loss > 50000:
        evidence += 4

    if candidate.zone == "RED":
        evidence -= 12

    return max(35, min(90, evidence))


def _calibrate_confidence(candidate: AiAuditCandidate, base_confidence: int) -> int:
    adjusted = _adjust_confidence(candidate, base_confidence)
    evidence = _evidence_confidence(candidate)
    blended = round(adjusted * 0.55 + evidence * 0.45)
    return max(35, min(92, blended))


def _postprocess_profile(candidate: AiAuditCandidate, profile: AiAnomalyProfile) -> AiAnomalyProfile:
    boosted_risk = min(100, profile.risk_score + _apply_boost(candidate))

    # Missing core identity signals should not produce absolute-risk outcomes.
    if not candidate.tax_id and candidate.owner_name_known is False:
        boosted_risk = min(boosted_risk, 92)

    adjusted_confidence = _calibrate_confidence(candidate, profile.decision_confidence)

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

    clean_batch = [
        {key: value for key, value in item.model_dump().items() if value is not None}
        for item in batch
    ]

    prompt = (
        "You are a financial monitoring analyst for a state taxation system.\n\n"

        "You analyze structured land and property data ONLY.\n\n"

        "COMMON RISK PATTERNS:\n"
        "- land used without registered real estate\n"
        "- undervalued property assessments\n"
        "- missing taxpayer identification\n"
        "- mismatch between land purpose and assets\n\n"

        "FOR EACH input item:\n"
        "Return EXACTLY one profile in the SAME ORDER.\n\n"

        "Each profile must contain:\n"
        "- risk_score (0..100)\n"
        "- ai_summary (one short factual sentence, max 200 chars)\n"
        "- decision_confidence (0..100)\n\n"

        "DECISION CONFIDENCE DEFINITION:\n"
        "- 100 = only one obvious interpretation exists\n"
        "- 70-90 = mostly clear, minor ambiguity\n"
        "- 40-70 = multiple plausible interpretations\n"
        "- 0-40 = highly ambiguous data\n\n"

        "RULES:\n"
        "- Use ONLY provided data\n"
        "- Do NOT invent facts\n"
        "- If data is missing → confidence must decrease\n"
        "- High confidence ONLY when there is a single clear explanation\n\n"

        "RISK SIGNALS:\n"
        "- missing tax_id\n"
        "- mismatch between purpose and assets\n"
        "- high potential_loss_uah\n"
        "- zone RED indicates elevated risk\n\n"

        f"Input data: {json.dumps(clean_batch, ensure_ascii=False)}"
    )

    messages = [
        ChatCompletionSystemMessageParam(role="system", content="Return structured output that matches the response schema."),
        ChatCompletionUserMessageParam(role="user", content=prompt),
    ]

    completion = await client.beta.chat.completions.parse(
        model="gpt-4.1",
        temperature=0.1,
        timeout=10,
        messages=messages,
        response_format=AiProfilesPayload,
    )

    payload = cast(Any, completion.choices[0].message.parsed)
    if payload is None:
        raise ValueError("OpenAI response parsing failed")

    profiles = payload.profiles
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