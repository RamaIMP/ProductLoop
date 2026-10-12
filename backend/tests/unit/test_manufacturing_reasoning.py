import json
from types import SimpleNamespace
import pytest
from app.models.manufacturing import EvidenceRequest,ManufacturingInterpretation
from app.services.manufacturing_evidence import build_package
from app.services import manufacturing_reasoning as service

def package():
    request=EvidenceRequest(issue_type='power_and_charging',start_date='2026-10-04',end_date='2026-10-10')
    p=build_package(request,{'complaints':[{'complaint_id':'c','created_at':'2026-10-05','issue_type':'power_and_charging','product_model':'X500','batch_reference':'B1','region':'India','symptoms':['not_charging']}],
        'end_of_line_tests':[{'unit_test_id':'T1','batch_id':'B1','acoustic_db':55,'gate_result':'pass'}]})
    return p

def answer(ref,batch='B1'):
    return ManufacturingInterpretation(summary='A possible connection issue needs inspection.',summary_evidence_refs=[ref],overall_conclusion='hypotheses_identified',hypotheses=[{
        'possible_cause':'Possible connection issue','affected_batches':[batch],'evidence_strength':'limited',
        'explanation':'Report alone does not establish the cause.','supporting_evidence_refs':[ref],
        'contradicting_evidence_refs':[],'missing_information':['Inspection results'],'recommended_checks':['Inspect connection']}])

def test_compaction_and_source_validation():
    p=package();payload,records=service.model_input(p)
    assert not any(r.source_table=='end_of_line_tests' and r.evidence_level=='batch_sample' for r in records)
    summary=next(r for r in records if r.evidence_level=='batch_sample_summary')
    assert summary.data['source_record_ids']==['T1']
    ref=records[0].evidence_ref
    assert service.validate_interpretation(answer(ref),records,p)
    with pytest.raises(ValueError):service.validate_interpretation(answer('invented'),records,p)
    with pytest.raises(ValueError):service.validate_interpretation(answer(ref,'invented'),records,p)

def test_text_only_call_and_cache(monkeypatch):
    p=package();_,records=service.model_input(p);calls=[]
    monkeypatch.setattr(service,'generate_evidence',lambda r:p)
    def call(**kwargs):
        calls.append(kwargs)
        assert isinstance(kwargs['contents'],str)
        assert json.loads(kwargs['contents'])['evidence']
        return SimpleNamespace(text=answer(records[0].evidence_ref).model_dump_json())
    monkeypatch.setattr(service,'client',lambda:SimpleNamespace(models=SimpleNamespace(generate_content=call)))
    service._cache.clear()
    first=service.analyse(p.analysis_request)
    second=service.analyse(p.analysis_request)
    assert first.llm_called and not first.cached and second.cached
    assert len(calls)==1
    service.analyse(p.analysis_request,refresh=True)
    assert len(calls)==2
    service._cache.clear()

def test_empty_scope_skips_gemini(monkeypatch):
    p=package();empty=build_package(p.analysis_request,{})
    monkeypatch.setattr(service,'generate_evidence',lambda r:empty)
    monkeypatch.setattr(service,'client',lambda:pytest.fail('Gemini must not run for empty evidence'))
    result=service.compute(p.analysis_request)
    assert not result.llm_called
    assert result.interpretation.overall_conclusion=='insufficient_evidence'
