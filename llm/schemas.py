from enum import Enum
from typing import List
from pydantic import BaseModel, Field, field_validator


class TriageLevel(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    UNKNOWN = "unknown"


class DiagnosisPayload(BaseModel):
    summary: str = Field(..., min_length=10, max_length=500)
    triage_level: TriageLevel = TriageLevel.UNKNOWN
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    likely_causes: List[str] = Field(default_factory=list, max_length=6)
    recommended_actions: List[str] = Field(default_factory=list, max_length=8)
    stop_driving_reasons: List[str] = Field(default_factory=list, max_length=5)
    follow_up_questions: List[str] = Field(default_factory=list, max_length=6)

    @field_validator("likely_causes", "recommended_actions", "stop_driving_reasons", "follow_up_questions")
    @classmethod
    def clean_list_items(cls, value: List[str]) -> List[str]:
        cleaned = []
        for item in value:
            text = (item or "").strip()
            if text:
                cleaned.append(text[:220])
        return cleaned[:8]
