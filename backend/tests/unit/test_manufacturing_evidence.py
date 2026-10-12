from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.main import app
from app.api import manufacturing
from app.models.manufacturing import EvidenceRequest,EvidencePackage
from app.services.manufacturing_evidence import build_package,unique,EvidenceTooLarge
from app.rules.dashboard_scope import DASHBOARD_ISSUE_TYPES

def request(issue='power_and_charging',region=None):
    return EvidenceRequest(issue_type=issue,start_date='2026-10-04',end_date='2026-10-10',region=region)

def complaint(id,when='2026-10-04T00:00:00Z',**patch):
    return {'complaint_id':id,'created_at':when,'product_model':'X500','issue_type':'power_and_charging','region':'India',
        'batch_reference':'B1','symptoms':['not_charging'],'safety_flag':False,**patch}

def test_counts_baseline_refs_and_completed_week_denominators():
    rows=[complaint('c1'),complaint('c2'),complaint('p1','2026-10-03T18:29:59Z'),complaint('boundary','2026-10-03T18:30:00Z')]
    source={'complaints':rows,'shipments_weekly':[
        {'batch_id':'B1','region':'India','week_start':'2026-09-21','units':100},
        {'batch_id':'B1','region':'India','week_start':'2026-10-05','units':900}]}
    p=build_package(request(),source)
    assert p.signal.current_complaints==3 and p.signal.previous_complaints==1
    assert p.signal.change_percent==200
    assert p.batch_comparisons[0].shipped_through_current_end==100
    assert p.batch_comparisons[0].current_reports_per_1000_shipped==30
    assert not p.llm_called
    EvidencePackage.model_validate_json(p.model_dump_json())

@pytest.mark.parametrize('issue',DASHBOARD_ISSUE_TYPES)
def test_all_supported_issues_and_missing_evidence(issue):
    p=build_package(request(issue),{'complaints':[complaint('c',issue_type=issue)]})
    assert p.signal.current_complaints==1
    assert p.signal.change_percent is None
    assert p.batch_comparisons[0].current_reports_per_1000_shipped is None
    assert any('No matching service_repairs' in l for l in p.limitations)

def test_region_empty_scope_duplicates_and_provenance():
    c=complaint('c')
    p=build_package(request(region='India'),{'complaints':[c,c,complaint('uk',region='UK')]},{'batches':{'data_origin':'simulated'}})
    assert p.signal.current_complaints==1
    assert any('simulated' in l for l in p.limitations)
    empty=build_package(request(region='France'),{'complaints':[c]})
    assert empty.status=='no_matching_complaints' and empty.signal.change_percent is None
    with pytest.raises(ValueError):unique('complaints',[c,{**c,'severity':'high'}])

def test_factory_summary_does_not_invent_spec_limits():
    p=build_package(request(),{'complaints':[complaint('c')],'end_of_line_tests':[
        {'unit_test_id':'T1','batch_id':'B1','gate_result':'fail','acoustic_db':63,'acoustic_limit_used_db':62,'vibration_rms_mm_s':2.1},
        {'unit_test_id':'T2','batch_id':'B1','gate_result':'pass','acoustic_db':59,'acoustic_limit_used_db':None,'vibration_rms_mm_s':1.1}]})
    s=p.factory_test_summaries[0]
    assert s.sample_count==2 and s.gate_fail_count==1
    assert s.measurements['acoustic_db']['mean']==61
    assert s.measurements['acoustic_db']['above_recorded_limit_count']==1
    assert 'above_recorded_limit_count' not in s.measurements['vibration_rms_mm_s']

def test_link_mismatch_and_invalid_reference_rejected():
    with pytest.raises(ValueError):build_package(request(),{'complaints':[complaint('c')],
        'service_repairs':[{'repair_id':'r','complaint_id':'c','batch_id':'other','region':'India'}]})
    p=build_package(request(),{'complaints':[complaint('c')]}).model_dump()
    p['batch_comparisons'][0]['evidence_refs']=['not-real']
    with pytest.raises(ValidationError):EvidencePackage.model_validate(p)

def test_api_validation_and_read_only_contract(monkeypatch):
    monkeypatch.setattr(manufacturing,'generate_evidence',lambda r:build_package(r,{}))
    client=TestClient(app)
    url='/api/manufacturing/evidence?issue_type=power_and_charging&start_date=2026-10-04&end_date=2026-10-10'
    r=client.get(url)
    assert r.status_code==200 and r.json()['llm_called'] is False
    assert client.get(url.replace('power_and_charging','shaving_performance')).status_code==422
    assert client.get(url.replace('2026-10-04','2026-10-11')).status_code==422
    assert TestClient(app,client=('192.0.2.1',1000)).get(url).status_code==403
    monkeypatch.setattr(manufacturing,'generate_evidence',lambda r:(_ for _ in ()).throw(EvidenceTooLarge('narrow range')))
    assert client.get(url).status_code==413

def test_snapshot_ids_are_deterministic():
    now=datetime(2026,10,10,tzinfo=timezone.utc)
    a=build_package(request(),{'complaints':[complaint('c')]},snapshot=now)
    b=build_package(request(),{'complaints':[complaint('c')]},snapshot=now)
    assert a.package_id==b.package_id
