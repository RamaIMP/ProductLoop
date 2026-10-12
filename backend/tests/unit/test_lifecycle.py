import json
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.api import consumer
from app.services import lifecycle, bigquery as sync
from app.models.taxonomy import Extraction

client = TestClient(app)
EXTRACTION = Extraction(symptoms=['hair_buildup'],confidence=0.9).model_dump(mode='json')
ID = 'PL-11111111-1111-4111-8111-111111111111'

def draft(user='lifecycle-test', **extra):
    response = client.post('/api/incidents',json={'user_id':user,'complaint_id':ID,**extra})
    assert response.status_code == 200
    return response.json()

def confirm():
    return client.post('/api/reports/confirm',json={'user_id':'lifecycle-test','complaint_id':ID,
        'extraction':EXTRACTION,'consent_share':True}).json()['report']

def events():
    return lifecycle.get_store().all('complaint_events')

def test_registration_reuse_and_unknown_details():
    payload = {'user_id':'lifecycle-test','serial_number':'SYNTHETIC-UNIT','product_model':'X500'}
    first = client.post('/api/units/register',json=payload).json()
    second = client.post('/api/units/register',json=payload).json()
    assert first == second and first['batch_id'] is None
    incident = draft(serial_number='SYNTHETIC-UNIT',incident_city='Test city')
    assert incident['unit_id'] == first['unit_id']
    assert incident['batch_reference'] is None and incident['location_source'] == 'user_provided'
    assert len(lifecycle.get_store().all('registered_units')) == 1
    assert client.post('/api/units/register',json={**payload,'user_id':'other'}).status_code == 409

def test_single_owned_device_is_inherited_by_new_complaint():
    store = lifecycle.get_store()
    unit = store.register({'consumer_id':'lifecycle-test','serial_number':'OWNED',
        'product_model':'X500','batch_id':'BATCH','region':'India'})
    incident = draft()
    assert incident['serial_number'] == 'OWNED'
    assert incident['unit_id'] == unit['unit_id']
    assert incident['batch_reference'] == 'BATCH'
    assert incident['region'] == 'India'
    assert incident.get('incident_country') is None
    assert draft() == incident
    row = lifecycle.complaint_row(incident)
    assert row['serial_number'] == 'OWNED' and row['batch_reference'] == 'BATCH'

def test_automatic_link_never_chooses_another_owner_or_unsupported_model():
    store = lifecycle.get_store()
    store.register({'consumer_id':'other','serial_number':'OTHER','product_model':'X500'})
    store.register({'consumer_id':'lifecycle-test','serial_number':'X700','product_model':'X700'})
    assert draft()['serial_number'] is None

def test_automatic_link_never_guesses_between_multiple_devices():
    store = lifecycle.get_store()
    for serial in ('A','B'):
        store.register({'consumer_id':'lifecycle-test','serial_number':serial,'product_model':'X500'})
    assert draft()['serial_number'] is None

def test_existing_incident_is_not_retroactively_linked():
    incident = draft()
    lifecycle.get_store().register({'consumer_id':'lifecycle-test','serial_number':'NEW','product_model':'X500'})
    assert draft() == incident

def test_complaint_summary_uses_findings_not_courtesy_text():
    store = lifecycle.get_store()
    draft()
    record = store.classify(ID, 'lifecycle-test', EXTRACTION, {}, message='thanks')
    assert 'hair buildup' in record['complaint_summary']
    assert 'thanks' not in record['complaint_summary']
    assert 'raw_complaint' not in store.get('complaints', ID)
    updated = store.save_report({**record, 'outcome':'not_fixed', 'ticket_id':'SR-TEST',
        'status':'ticket_raised', 'raw_complaint':'thanks'}, 'ticket_raised')
    assert 'not fixed' in updated['complaint_summary']
    assert 'Support ticket raised' in updated['complaint_summary']
    assert 'raw_complaint' not in updated
    cloud = lifecycle.complaint_row(updated)
    assert cloud['raw_complaint'] is None
    assert cloud['complaint_summary'] == updated['complaint_summary']
    resolved = store.save_report({**updated,'status':'resolved'}, 'resolved')
    assert 'marked the issue resolved' in resolved['complaint_summary']
    assert 'not fixed' not in resolved['complaint_summary']

def test_summary_does_not_invent_findings_for_greetings():
    assert lifecycle.complaint_summary({'raw_complaint':'hi'}) is None

def test_draft_confirm_and_event_idempotency():
    draft()
    draft()
    assert not lifecycle.complaint_row(lifecycle.get_store().get('complaints',ID))['counts_as_complaint']
    assert client.get('/api/reports?user_id=lifecycle-test').json() == []
    first = confirm()
    second = confirm()
    assert first == second and first['report_id'] == ID
    assert [e['event_type'] for e in events()] == ['incident_started','report_submitted']
    assert lifecycle.complaint_row(first)['counts_as_complaint']
    assert len(client.get('/api/reports?user_id=lifecycle-test').json()) == 1

def test_greeting_creates_no_incident():
    response = client.post('/api/conversation',json={'user_id':'test','message':'hi'})
    assert response.status_code == 200
    assert lifecycle.get_store().all('complaints') == []

def test_evidence_fields_merge_independently_and_survive_restart(tmp_path):
    store = lifecycle.LifecycleStore(str(tmp_path / 'state.db'))
    store.draft('u',ID)
    store.evidence_start('ev-test',ID,'u','test.jpg','image/jpeg')
    store.evidence_update('ev-test',{'storage_status':'uploaded','gcs_uri':'gs://test/test.jpg'},'evidence_stored')
    store.evidence_update('ev-test',{'extraction_status':'completed','extracted_symptoms':['hair_buildup']},'evidence_analysed')
    store.db.close()
    reopened = lifecycle.LifecycleStore(str(tmp_path / 'state.db'))
    record = reopened.get('evidence','ev-test')
    assert record['gcs_uri'] == 'gs://test/test.jpg' and record['extracted_symptoms'] == ['hair_buildup']
    assert len(reopened.pending()) == 8
    reopened.db.close()

def test_failed_sync_retains_queue_and_retry_acks(monkeypatch):
    draft()
    before = lifecycle.get_store().pending()
    class Failing:
        def write(self, batch):
            raise RuntimeError('offline')
    import pytest
    with pytest.raises(RuntimeError):
        sync.flush_once(Failing())
    assert lifecycle.get_store().pending() == before
    class Success:
        def write(self,batch):
            assert batch == before
    assert sync.flush_once(Success())
    assert lifecycle.get_store().pending() == []

def test_outcomes_callback_and_restart_records():
    draft(); confirm()
    payload = {'user_id':'lifecycle-test','report_id':ID}
    client.post('/api/conversation',json={**payload,'event':'not_resolved'})
    client.post('/api/conversation',json={**payload,'event':'not_resolved'})
    client.post('/api/conversation',json={**payload,'event':'create_ticket'})
    client.post('/api/conversation',json={**payload,'event':'create_ticket'})
    start = datetime.now(timezone.utc) + timedelta(days=1)
    request = {'user_id':'lifecycle-test','slot':'Test future slot','scheduled_start':start.isoformat(),
               'scheduled_end':(start+timedelta(minutes=30)).isoformat(),'time_zone':'Asia/Kolkata'}
    callback = client.post(f'/api/reports/{ID}/callback',json=request)
    assert callback.status_code == 200
    assert callback.json()['callback']['status'] == 'demo_requested'
    client.post(f'/api/reports/{ID}/callback',json=request)
    client.post('/api/conversation',json={**payload,'event':'resolved'})
    record = lifecycle.get_store().get('complaints',ID)
    assert record['status'] == 'resolved' and record['resolved_at']
    types = [e['event_type'] for e in events()]
    assert types.count('not_resolved') == types.count('ticket_raised') == types.count('callback_requested') == 1

def test_owner_and_unknown_unit_validation():
    draft()
    assert client.post('/api/incidents',json={'user_id':'other','complaint_id':ID}).status_code == 404
    assert client.post('/api/conversation',json={'user_id':'other','complaint_id':ID,'message':'hello'}).status_code == 404
    assert client.post('/api/incidents',json={'user_id':'other','complaint_id':'PL-'+'2'*32,'serial_number':'unknown'}).status_code == 409

def test_abandoned_draft_is_not_counted():
    draft()
    response = client.post(f'/api/incidents/{ID}/abandon?user_id=lifecycle-test')
    assert response.json()['status'] == 'abandoned'
    assert not lifecycle.complaint_row(response.json())['counts_as_complaint']

def test_interrupted_media_is_not_left_pending():
    store = lifecycle.get_store()
    store.draft('u',ID)
    store.evidence_start('ev-test',ID,'u','test.jpg','image/jpeg')
    store.recover_interrupted()
    record = store.get('evidence','ev-test')
    assert record['storage_status'] == record['extraction_status'] == 'failed'

def test_callback_slots_are_future_and_have_timezone():
    response = client.get('/api/callback-slots').json()
    assert len(response) == 3
    for slot in response:
        assert datetime.fromisoformat(slot['scheduled_start']) > datetime.now(timezone.utc)
        assert slot['time_zone'] == 'Asia/Kolkata'

def test_media_retry_does_not_duplicate_or_reanalyse(monkeypatch):
    from app.services import media_jobs
    draft()
    calls = []
    async def upload(_):
        return 'gs://test/synthetic.jpg'
    def extract(*args):
        calls.append(args)
        return Extraction(symptoms=['hair_buildup'],confidence=0.9)
    monkeypatch.setattr(media_jobs,'store_uploaded_media',upload)
    monkeypatch.setattr(consumer,'extract_from_bytes',extract)
    form = {'user_id':'lifecycle-test','complaint_id':ID,'evidence_id':'ev_'+'a'*32}
    with TestClient(app) as session:
        first = session.post('/api/media/extract',data=form,files={'file':('test.jpg',b'test','image/jpeg')})
        second = session.post('/api/media/extract',data=form,files={'file':('test.jpg',b'test','image/jpeg')})
        assert first.status_code == second.status_code == 200
        assert first.json()['evidence_id'] == second.json()['evidence_id']
        assert session.post('/api/media/extract',data=form,files={'file':('test.jpg',b'changed','image/jpeg')}).status_code == 409
    assert len(calls) == 1
    assert len(lifecycle.get_store().all('evidence')) == 1

def test_new_media_preserves_server_side_previous_evidence(monkeypatch):
    from app.services import media_jobs
    draft()
    store = lifecycle.get_store()
    store.classify(ID,'lifecycle-test',EXTRACTION,{'issue_type':'cleaning_and_maintenance','severity':'low','safety_flag':False})
    async def upload(_):
        return 'gs://test/test.jpg'
    monkeypatch.setattr(media_jobs,'store_uploaded_media',upload)
    monkeypatch.setattr(consumer,'extract_from_bytes',lambda *args: Extraction(symptoms=['visible_damage'],confidence=0.9))
    with TestClient(app) as session:
        response = session.post('/api/media/extract',data={'user_id':'lifecycle-test','complaint_id':ID},
            files={'file':('test.jpg',b'test','image/jpeg')})
    assert response.status_code == 200
    assert set(response.json()['extraction']['symptoms']) == {'hair_buildup','visible_damage'}

def test_bigquery_merge_uses_parameters_and_append_only_events():
    from google.cloud import bigquery
    class Job:
        def result(self):
            return []
    class Table:
        schema = [bigquery.SchemaField('complaint_id','STRING'),bigquery.SchemaField('event_id','STRING'),
                  bigquery.SchemaField('event_type','STRING')]
    class Fake:
        def get_table(self,table):
            return Table()
        def query(self,query,job_config):
            assert 'BEGIN TRANSACTION' in query and 'COMMIT TRANSACTION' in query
            assert 'WHEN MATCHED' not in query
            assert 'malicious' not in query
            assert 'malicious' in job_config.query_parameters[0].value
            return Job()
    writer = sync.Writer(Fake())
    writer.write([(1,'complaint_events','e',json.dumps({'event_id':'e','complaint_id':ID,'event_type':"malicious ' input"}))])

def test_report_details_scoped_to_owner_and_excludes_private_storage_payload():
    draft(); confirm()
    store = lifecycle.get_store()
    store.evidence_start('ev-details',ID,'lifecycle-test','sample.jpg','image/jpeg')
    store.evidence_update('ev-details',{'gcs_uri':'gs://private/file','api_result':{'secret':'not-for-detail-view'}},'evidence_stored')
    result = client.get(f'/api/reports/{ID}?user_id=lifecycle-test')
    assert result.status_code == 200
    assert result.json()['report']['report_id'] == ID
    assert len(result.json()['evidence']) == 1
    assert 'gcs_uri' not in result.json()['evidence'][0]
    assert 'api_result' not in result.json()['evidence'][0]
    assert result.json()['events'][0]['event_type'] == 'incident_started'
    assert client.get(f'/api/reports/{ID}?user_id=someone-else').status_code == 404

def test_unsubmitted_draft_is_not_a_report_detail():
    draft()
    assert client.get(f'/api/reports/{ID}?user_id=lifecycle-test').status_code == 404

def test_multiple_registered_devices_link_to_distinct_incidents():
    for serial in ('DEVICE-A','DEVICE-B'):
        result = client.post('/api/units/register',json={'user_id':'multi','serial_number':serial,'product_model':'X500','region':'Registered region'})
        assert result.status_code == 200
    assert len(client.get('/api/units?user_id=multi').json()) == 2
    assert client.get('/api/units?user_id=other').json() == []
    a = client.post('/api/incidents',json={'user_id':'multi','complaint_id':ID,'serial_number':'DEVICE-A'}).json()
    b = client.post('/api/incidents',json={'user_id':'multi','complaint_id':'PL-'+'b'*32,'serial_number':'DEVICE-B'}).json()
    assert a['unit_id'] != b['unit_id']
    assert a['region'] == 'Registered region'
    assert a.get('incident_region') is None
    assert client.post('/api/incidents',json={'user_id':'multi','complaint_id':ID,'serial_number':'DEVICE-B'}).status_code == 409

def test_other_model_can_register_but_cannot_use_x500_knowledge():
    response = client.post('/api/units/register',json={'user_id':'multi','serial_number':'OTHER-MODEL','product_model':' x700 '})
    assert response.json()['product_model'] == 'X700'
    response = client.post('/api/incidents',json={'user_id':'multi','complaint_id':ID,'serial_number':'OTHER-MODEL'})
    assert response.status_code == 409
    assert 'knowledge base' in response.json()['detail']
    assert client.post('/api/units/register',json={'user_id':'multi','serial_number':'OTHER-MODEL','product_model':'X500'}).status_code == 409

def test_profile_reads_registered_database_for_current_user(monkeypatch):
    from datetime import date, datetime, timezone
    monkeypatch.setattr(sync,'enabled',lambda: True)
    seen = []
    def read(user_id):
        seen.append(user_id)
        return [{'product_model':'X500','consumer_id':user_id,'serial_number':'SAVED-SERIAL',
                 'purchase_date':date(2026,8,12),'registered_at':datetime(2026,9,1,tzinfo=timezone.utc)}]
    monkeypatch.setattr(sync,'read_profile_units',read)
    response = client.get('/api/profile/registered-units?user_id=owner')
    assert response.status_code == 200
    assert seen == ['owner']
    assert response.json()['source'] == 'bigquery.registered_units'
    assert response.json()['units'][0]['purchase_date'] == '2026-08-12'
    assert lifecycle.get_store().all('registered_units') == []

def test_profile_database_failure_not_reported_as_missing_registration(monkeypatch):
    monkeypatch.setattr(sync,'enabled',lambda: True)
    def fail(_):
        raise RuntimeError('unavailable')
    monkeypatch.setattr(sync,'read_profile_units',fail)
    response = client.get('/api/profile/registered-units?user_id=owner')
    assert response.status_code == 503
    assert 'units' not in response.json()

def test_profile_database_query_is_owner_scoped_and_parameterized():
    class Job:
        def result(self,timeout):
            assert timeout == 20
            return []
    class Fake:
        def query(self,query,job_config):
            assert 'WHERE consumer_id = @user_id' in query
            assert "UPPER(TRIM(product_model)) = 'X500'" in query
            assert "owner' OR TRUE" not in query
            assert job_config.query_parameters[0].value == "owner' OR TRUE"
            return Job()
    assert sync.read_profile_units("owner' OR TRUE",Fake()) == []
