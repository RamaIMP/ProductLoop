"""Contracts for manufacturing evidence and explicitly unconfirmed hypotheses."""
from datetime import date, datetime, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator
from app.rules.dashboard_scope import DASHBOARD_ISSUE_TYPES

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)

class EvidenceRequest(StrictModel):
    product_model: Literal['X500']='X500'
    issue_type: str
    start_date: date
    end_date: date
    region: str | None=None

    @field_validator('issue_type')
    @classmethod
    def supported_issue(cls,value):
        if value not in DASHBOARD_ISSUE_TYPES: raise ValueError('Issue is outside manufacturer dashboard scope')
        return value

    @field_validator('region')
    @classmethod
    def clean_region(cls,value):
        if value is None:return None
        value=value.strip()
        if len(value)>100:raise ValueError('Region is too long')
        return value or None

    @model_validator(mode='after')
    def valid_window(self):
        if not 1<=(self.end_date-self.start_date).days+1<=366:raise ValueError('Choose a range of 1 to 366 days')
        return self

    @property
    def baseline_start(self):return self.start_date-timedelta(days=(self.end_date-self.start_date).days+1)

class EvidenceRecord(StrictModel):
    evidence_ref: str
    source_table: str
    source_record_key: dict[str,str]
    evidence_level: str
    data: dict[str,JsonValue]

class CountComparison(StrictModel):
    current_complaints: int=Field(ge=0)
    previous_complaints: int=Field(ge=0)
    change_percent: float | None
    current_safety_count: int=Field(ge=0)
    symptoms: dict[str,int]
    current_complaint_ids: list[str]
    previous_complaint_ids: list[str]

class BatchComparison(StrictModel):
    batch_id: str | None
    current_complaints: int
    previous_complaints: int
    change_percent: float | None
    current_share_percent: float | None
    shipped_through_current_end: int | None
    shipped_through_previous_end: int | None
    current_reports_per_1000_shipped: float | None
    previous_reports_per_1000_shipped: float | None
    evidence_refs: list[str]

class FactorySummary(StrictModel):
    batch_id: str
    sample_count: int
    gate_fail_count: int
    measurements: dict[str,dict[str,JsonValue]]
    evidence_refs: list[str]

class EvidencePackage(StrictModel):
    schema_version: Literal['1.0']='1.0'
    package_id: str
    generated_at: datetime
    source_snapshot_at: datetime
    analysis_request: EvidenceRequest
    baseline_start: date
    baseline_end: date
    time_zone: Literal['Asia/Kolkata']='Asia/Kolkata'
    evidence_cutoff: date
    status: Literal['evidence_ready','no_matching_complaints']
    signal: CountComparison
    batch_comparisons: list[BatchComparison]
    factory_test_summaries: list[FactorySummary]
    evidence: list[EvidenceRecord]
    source_counts: dict[str,int]
    source_provenance: dict[str,dict[str,str]]
    limitations: list[str]
    llm_called: Literal[False]=False

    @model_validator(mode='after')
    def valid_references(self):
        refs={r.evidence_ref for r in self.evidence}
        if len(refs)!=len(self.evidence):raise ValueError('Duplicate evidence reference')
        for group in [*self.batch_comparisons,*self.factory_test_summaries]:
            if not set(group.evidence_refs)<=refs:raise ValueError('Unknown evidence reference')
        if len(self.signal.current_complaint_ids)!=self.signal.current_complaints:raise ValueError('Current count mismatch')
        if len(self.signal.previous_complaint_ids)!=self.signal.previous_complaints:raise ValueError('Previous count mismatch')
        if sum(b.current_complaints for b in self.batch_comparisons)!=self.signal.current_complaints:raise ValueError('Batch totals mismatch')
        return self

class ManufacturingHypothesis(StrictModel):
    possible_cause: str=Field(min_length=1,max_length=500)
    affected_batches: list[str]
    evidence_strength: Literal['limited','moderate','strong']
    explanation: str=Field(min_length=1,max_length=2000)
    supporting_evidence_refs: list[str]=Field(min_length=1)
    contradicting_evidence_refs: list[str]
    missing_information: list[str]
    recommended_checks: list[str]

class ManufacturingInterpretation(StrictModel):
    summary: str=Field(min_length=1,max_length=3000)
    summary_evidence_refs: list[str]
    hypotheses: list[ManufacturingHypothesis]=Field(max_length=4)
    overall_conclusion: Literal['hypotheses_identified','insufficient_evidence']

    @model_validator(mode='after')
    def conclusion_matches(self):
        if self.overall_conclusion=='hypotheses_identified' and not self.hypotheses:
            raise ValueError('Hypotheses required for this conclusion')
        return self

class ManufacturingAnalysis(StrictModel):
    analysis_request: EvidenceRequest
    package_id: str
    model: str
    prompt_version: str
    generated_at: datetime
    evidence_snapshot_at: datetime
    cached: bool=False
    llm_called: bool
    interpretation: ManufacturingInterpretation
    evidence: list[EvidenceRecord]
    limitations: list[str]
