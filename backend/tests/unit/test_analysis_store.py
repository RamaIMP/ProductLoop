from copy import deepcopy
from datetime import datetime,timezone,timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.api import manufacturing
from app.services import analysis_store as store
from app.models.manufacturing import EvidenceRequest
from app.services.manufacturing_evidence import build_package

def req(region=None):return EvidenceRequest(issue_type='power_and_charging',start_date='2026-10-04',end_date='2026-10-10',region=region)
def package():return build_package(req(),{'complaints':[{'complaint_id':'c','created_at':'2026-10-05','product_model':'X500','issue_type':'power_and_charging','batch_reference':'B1','region':'India','symptoms':['not_charging']}]})

def test_fingerprint_ignores_clock_but_tracks_evidence_and_scope():
    a=package();b=a.model_copy(update={'generated_at':a.generated_at+timedelta(seconds=10),'source_snapshot_at':a.source_snapshot_at+timedelta(seconds=10),'package_id':'different'})
    assert store.fingerprint(a)==store.fingerprint(b)
    c=a.model_copy(deep=True);c.evidence[0].data['symptoms']=['slow_charging']
    assert store.fingerprint(a)!=store.fingerprint(c)
    assert store.scope_key(req())!=store.scope_key(req('India'))

def test_unchanged_scope_does_not_invoke_model(monkeypatch):
    p=package();calls=[]
    monkeypatch.setattr(store,'Writer',lambda:type('W',(),{'prefix':'test.ds'})())
    monkeypatch.setattr(store,'generate_evidence',lambda r:p)
    monkeypatch.setattr(store,'compute',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('No Gemini for unchanged evidence')))
    def query(w,sql,**values):
        calls.append(sql)
        if sql.startswith('SELECT analysis_id'):return [{'analysis_id':'a','evidence_fingerprint':store.fingerprint(p),'analysis_version':1}]
        return []
    monkeypatch.setattr(store,'query',query)
    store.process_scope({'scope_key':store.scope_key(req()),'request_json':req().model_dump(mode='json'),'requested_at':datetime.now(timezone.utc)})
    assert any("status='ready'" in q for q in calls)
    assert not any('INSERT INTO' in q for q in calls)

def test_reads_and_enqueue_do_not_invoke_model(monkeypatch):
    monkeypatch.setattr(store,'compute',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('No model in API')))
    monkeypatch.setattr(store,'saved',lambda r:{'status':'ready','analysis':None})
    monkeypatch.setattr(store,'subscribe',lambda r:{'status':'pending'})
    client=TestClient(app)
    r=client.get('/api/manufacturing/analysis?issue_type=power_and_charging&start_date=2026-10-04&end_date=2026-10-10')
    assert r.status_code==200 and r.json()['status']=='ready'
    r=client.post('/api/manufacturing/analysis',json=req().model_dump(mode='json'))
    assert r.status_code==202

def test_changed_evidence_appends_a_new_version(monkeypatch):
    p=package();calls=[]
    monkeypatch.setattr(store,'Writer',lambda:type('W',(),{'prefix':'test.ds'})())
    monkeypatch.setattr(store,'generate_evidence',lambda r:p)
    class Result:
        model='test-model';prompt_version='test-prompt'
        def model_dump(self,**kwargs):return {'test':'analysis'}
    monkeypatch.setattr(store,'compute',lambda *a,**kw:Result())
    def query(w,sql,**values):
        calls.append((sql,values))
        if sql.startswith('SELECT analysis_id'):return [{'analysis_id':'old','evidence_fingerprint':'different','analysis_version':3}]
        return []
    monkeypatch.setattr(store,'query',query)
    store.process_scope({'scope_key':store.scope_key(req()),'request_json':req().model_dump(mode='json'),'requested_at':datetime.now(timezone.utc)})
    writes=[values for sql,values in calls if 'INSERT INTO' in sql]
    assert len(writes)==1 and writes[0]['version']=='4'
    assert writes[0]['evidence']['package_id']==p.package_id
    assert any("status='ready'" in sql for sql,_ in calls)

def test_review_attaches_to_specific_analysis(monkeypatch):
    calls=[]
    monkeypatch.setattr(store,'review',lambda id,**kwargs:calls.append((id,kwargs)) or {'review_id':'r'})
    c=TestClient(app)
    r=c.post('/api/manufacturing/analyses/a-v1/reviews',json={'hypothesis_index':0,'verdict':'needs_more_evidence','comment':'Inspect connector first'})
    assert r.status_code==201 and calls[0][0]=='a-v1'
    assert c.post('/api/manufacturing/analyses/a-v1/reviews',json={'hypothesis_index':0,'verdict':'confirmed','comment':'x'}).status_code==422


def prior(p):
    return {'evidence_json':p.model_dump(mode='json'),'evidence_fingerprint':store.fingerprint(p)}


def test_count_dates_status_and_duplicate_reports_do_not_trigger():
    a=package();b=a.model_copy(deep=True)
    b.analysis_request=req().model_copy(update={'start_date':req().start_date+timedelta(days=2),'end_date':req().end_date+timedelta(days=2)})
    b.signal.current_complaints+=1
    b.evidence[0].data.update(status='ticket_raised',created_at='2026-10-12',complaint_summary='Support ticket raised')
    b.evidence.append(b.evidence[0].model_copy(update={'evidence_ref':'new','source_record_key':{'complaint_id':'another'}}))
    assert store.fingerprint(a)==store.fingerprint(b)
    assert not store.meaningful_change(b,prior(a))


def test_new_symptom_batch_or_safety_triggers():
    for update in ({'symptoms':['slow_charging']},{'batch_reference':'B2'},{'safety_flag':True}):
        a=package();b=a.model_copy(deep=True);b.evidence[0].data.update(update)
        assert store.meaningful_change(b,prior(a))


def test_relevant_factory_edits_and_deletion_trigger_unrelated_changes_do_not():
    from app.models.manufacturing import EvidenceRecord
    a=package()
    a.evidence.append(EvidenceRecord(evidence_ref='LOT',source_table='batch_lots',source_record_key={'batch_id':'B1','component':'battery_pack','lot_id':'L1'},evidence_level='batch_component_mapping',data={'batch_id':'B1','component':'battery_pack','supplier':'S1','quantity':100}))
    b=a.model_copy(deep=True);b.evidence[-1].data['quantity']=101
    assert not store.meaningful_change(b,prior(a))
    b.evidence[-1].data['supplier']='S2'
    assert store.meaningful_change(b,prior(a))
    assert store.meaningful_change(package(),prior(a))
    b=a.model_copy(deep=True)
    b.evidence.append(EvidenceRecord(evidence_ref='OTHER',source_table='batch_lots',source_record_key={'lot_id':'other'},evidence_level='batch_component_mapping',data={'batch_id':'B1','component':'housing','supplier':'new'}))
    assert not store.meaningful_change(b,prior(a))


def test_new_media_finding_triggers_but_repeat_does_not():
    from app.models.manufacturing import EvidenceRecord
    a=package();b=a.model_copy(deep=True)
    b.evidence.append(EvidenceRecord(evidence_ref='MEDIA',source_table='evidence',source_record_key={'evidence_id':'e'},evidence_level='media_extraction_not_reanalysed',data={'complaint_id':'c','extracted_summary':'Damaged charging connector','extracted_symptoms':['not_charging']}))
    assert store.meaningful_change(b,prior(a))
    c=b.model_copy(deep=True);c.evidence.append(c.evidence[-1].model_copy(update={'evidence_ref':'MEDIA2','source_record_key':{'evidence_id':'e2'}}))
    assert not store.meaningful_change(c,prior(b))


def test_expiring_complaints_do_not_trigger():
    a=package();b=build_package(req(),{})
    assert not store.meaningful_change(b,prior(a))


def test_saved_reference_preserves_original_scope_and_reviews(monkeypatch):
    p=package();analysis={'analysis_request':req().model_dump(mode='json')}
    monkeypatch.setattr(store,'Writer',lambda:type('W',(),{'prefix':'test.ds'})())
    monkeypatch.setattr(store,'query',lambda *a,**k:[])
    monkeypatch.setattr(store,'related_analysis',lambda *a:{'analysis_id':'original','analysis_version':2,'analysis_json':analysis,'evidence_json':p.model_dump(mode='json')})
    result=store.saved(req().model_copy(update={'end_date':req().end_date+timedelta(days=2)}))
    assert result['status']=='saved_reference'
    assert result['reused_for_scope'] is True
    assert result['analysis']['analysis_request']['end_date']=='2026-10-10'
    assert 'evidence_json' not in result


def test_reuse_across_dates_does_not_call_gemini_or_append(monkeypatch):
    p=package();calls=[]
    monkeypatch.setattr(store,'Writer',lambda:type('W',(),{'prefix':'test.ds'})())
    monkeypatch.setattr(store,'generate_evidence',lambda r:p)
    monkeypatch.setattr(store,'related_analysis',lambda w,r:prior(p))
    monkeypatch.setattr(store,'compute',lambda *a,**k:(_ for _ in ()).throw(AssertionError('No Gemini')))
    monkeypatch.setattr(store,'query',lambda w,sql,**k:calls.append(sql) or [])
    store.process_scope({'scope_key':'new-window','request_json':req().model_dump(mode='json'),'requested_at':datetime.now(timezone.utc)})
    assert any("status='ready'" in sql for sql in calls)
    assert not any('INSERT INTO' in sql for sql in calls)
