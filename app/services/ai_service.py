import os
import json
import asyncio
from typing import Optional, List, Tuple

from pydantic import BaseModel, Field, field_validator
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class AIInputData(BaseModel):
    cadastral_number: str
    area_ha: float
    valuation: float
    ownership_type: str
    purpose: str

    tax_id: Optional[str] = None
    owner_name: Optional[str] = None

    real_estate_area: Optional[float] = None
    real_estate_objects: Optional[int] = None

    @field_validator("area_ha")
    @classmethod
    def validate_area(cls, v):
        if v <= 0:
            raise ValueError("Area must be > 0")
        return v

    @field_validator("valuation")
    @classmethod
    def validate_valuation(cls, v):
        if v < 0:
            raise ValueError("Valuation cannot be negative")
        return v

    @field_validator("real_estate_area")
    @classmethod
    def validate_real_estate_area(cls, v):
        if v is not None and v < 0:
            raise ValueError("Real estate area cannot be negative")
        return v


class AIAnomalyProfile(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    ai_summary: str = Field(max_length=200)

    decision_confidence: int = Field(
        ge=0,
        le=100,
        description="0 = highly ambiguous, 100 = fully unambiguous"
    )


SYSTEM_PROMPT = """
You are a financial monitoring analyst for a state taxation system.

You analyze structured real estate and land data ONLY.

COMMON RISK PATTERNS:
- land used without registered real estate
- undervalued property assessments
- missing taxpayer identification
- mismatch between land purpose and assets

TASK 1:
Estimate tax evasion risk from 0 to 100.

TASK 2:
Generate a short explanation of the main anomaly.

TASK 3 (DECISION CONFIDENCE):
Estimate how unambiguous the interpretation of this record is.

Scale:
- 100 = only one obvious interpretation exists
- 70-90 = mostly clear, minor ambiguity
- 40-70 = multiple plausible interpretations
- 0-40 = highly ambiguous data

RULES:
- Do NOT invent facts
- Use ONLY provided input
- If data is missing → confidence must decrease

OUTPUT FORMAT:
risk_score: integer (0-100)
ai_summary: one sentence (max 200 chars)
decision_confidence: integer (0-100)
"""


class AnomalyDetectorAI:

    # -------------------------
    # SINGLE ANALYSIS
    # -------------------------
    @staticmethod
    async def analyze_record(data: AIInputData) -> AIAnomalyProfile:

        clean_data = {
            k: v for k, v in data.model_dump().items()
            if v is not None
        }

        try:
            response = await client.beta.chat.completions.parse(
                model="gpt-4.1",
                temperature=0.1,
                timeout=10,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(clean_data, ensure_ascii=False)
                    }
                ],
                response_format=AIAnomalyProfile
            )

            result = response.choices[0].message.parsed

        except Exception as e:
            return AIAnomalyProfile(
                risk_score=50,
                ai_summary=f"Fallback error: {str(e)[:60]}",
                decision_confidence=0
            )

        return AnomalyDetectorAI._postprocess(result, data)

    @staticmethod
    async def analyze_batch(
        items: List[AIInputData]
    ) -> Tuple[AIAnomalyProfile, ...]:

        results: List[AIAnomalyProfile] = []

        for i in range(0, len(items), 5):
            batch = items[i:i + 5]

            tasks = [
                AnomalyDetectorAI.analyze_record(item)
                for item in batch
            ]

            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)

        return tuple(results)

    @staticmethod
    def _postprocess(result: AIAnomalyProfile, data: AIInputData):

        boost = AnomalyDetectorAI._apply_boost(data)
        result.risk_score = min(100, result.risk_score + boost)

        result.decision_confidence = AnomalyDetectorAI._adjust_confidence(data, result)

        return AnomalyDetectorAI._guard(result)

    @staticmethod
    def _apply_boost(data: AIInputData) -> int:
        boost = 0

        if data.area_ha > 2 and not data.real_estate_area:
            boost += 20

        if not data.tax_id:
            boost += 15

        if data.area_ha and data.valuation:
            price_per_ha = data.valuation / data.area_ha
            if price_per_ha < 1000:
                boost += 10

        if "комерц" in data.purpose.lower() and not data.real_estate_area:
            boost += 15

        return boost

    @staticmethod
    def _adjust_confidence(data: AIInputData, result: AIAnomalyProfile) -> int:
        confidence = result.decision_confidence

        if not data.tax_id:
            confidence -= 10

        if not data.real_estate_area:
            confidence -= 10

        if data.area_ha > 5 and not data.real_estate_objects:
            confidence -= 5

        if data.real_estate_area and data.real_estate_objects:
            confidence += 5

        return max(0, min(100, confidence))

    @staticmethod
    def _guard(result: AIAnomalyProfile) -> AIAnomalyProfile:

        result.risk_score = max(0, min(100, result.risk_score))
        result.decision_confidence = max(0, min(100, result.decision_confidence))

        if len(result.ai_summary) > 200:
            result.ai_summary = result.ai_summary[:200]

        if not result.ai_summary.strip():
            result.ai_summary = "Insufficient data for conclusion."

        return result