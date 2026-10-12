"""Pydantic models built from the taxonomy. backend/app/taxonomy_v2.json is a copy of data/taxonomy_v2.json (a test keeps them identical).
Categories are never written in code: add a symptom to the JSON and every model, prompt and rule sees it."""
import json
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TAXONOMY = json.loads((Path(__file__).resolve().parent.parent / "taxonomy_v2.json").read_text())
SYMPTOM_INFO: dict = TAXONOMY["symptoms"]
ISSUE_TYPES: tuple = tuple(TAXONOMY["issue_types"])
ISSUE_PRIORITY: list = TAXONOMY["derivation_rules"]["issue_type_priority"]

IssueType = Enum("IssueType", {k: k for k in ISSUE_TYPES}, type=str)
Symptom = Enum("Symptom", {k: k for k in SYMPTOM_INFO}, type=str)
UserIntent = Enum("UserIntent", {k: k for k in TAXONOMY["user_intents"]}, type=str)
Onset = Enum("Onset", {v: v for v in TAXONOMY["context"]["onset"]}, type=str)
PersistsAfterCleaning = Enum("PersistsAfterCleaning", {v: v for v in TAXONOMY["context"]["persists_after_cleaning"]}, type=str)
Severity = Enum("Severity", {"low": "low", "medium": "medium", "high": "high"}, type=str)


class Context(BaseModel):
    onset: Onset = Onset("unknown")
    persists_after_cleaning: PersistsAfterCleaning = PersistsAfterCleaning("not_tried")
    during_charging: bool | None = None


class SpeechUnderstanding(BaseModel):
    status: Literal['understood', 'unclear', 'no_speech']
    intent: Literal['greeting', 'vague_problem', 'specific_problem', 'question', 'other']
    message: str = Field(default='', max_length=2000)
    reply: str = Field(min_length=1, max_length=1000)


class Extraction(BaseModel):
    """What Gemini returns. Issue type, severity and safety flag are NOT here: code derives them."""

    product_model: str = "X500"
    user_intent: UserIntent = UserIntent("report_problem")
    symptoms: list[Symptom] = Field(min_length=1)
    context: Context = Context()
    confidence: float = Field(ge=0.0, le=1.0)
    complaint_summary: str | None = Field(default=None, max_length=2000)
    retrieval_query: str | None = Field(default=None, max_length=1500)
    media_findings: 'MediaFindings | None' = None
    speech: SpeechUnderstanding | None = None

    @field_validator('complaint_summary', 'retrieval_query')
    @classmethod
    def _trim_optional_text(cls, value):
        return value.strip() or None if value is not None else None

    @field_validator("symptoms")
    @classmethod
    def _unique(cls, v):
        unique = list(dict.fromkeys(v))
        return [s for s in unique if s.value != 'unclear_description'] if len(unique) > 1 else unique


class Derived(BaseModel):
    issue_type: IssueType
    severity: Severity
    safety_flag: bool


class MediaFindings(BaseModel):
    """Observations from the newly supplied file, not the full incident history."""
    summary: str = Field(min_length=1, max_length=2000)
    symptoms: list[Symptom] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0, le=1)


Extraction.model_rebuild()
