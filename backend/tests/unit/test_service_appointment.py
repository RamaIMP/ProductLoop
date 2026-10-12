from fastapi.testclient import TestClient
from app.main import app
from app.services.lifecycle import get_store

client = TestClient(app)
ID = 'PL-' + 'd' * 32

def setup_report(status='ticket_raised', submitted=True):
    store = get_store()
    report = store.draft('appointment-test', ID)
    return store.save_report({**report, 'status':status, 'submitted_at':'2026-10-01T10:00:00Z' if submitted else None}, 'test_setup')

def payload():
    slot = client.get('/api/callback-slots').json()[0]
    return {'user_id':'appointment-test', 'centre_id':'central', 'scheduled_start':slot['scheduled_start']}

def test_booking_is_durable_idempotent_and_does_not_resolve_report():
    setup_report()
    data = payload()
    first = client.post(f'/api/reports/{ID}/service-appointment', json=data)
    assert first.status_code == 200
    assert first.json()['status'] == 'demo_booked'
    assert first.json()['booking_id'].startswith('DEMO-APT-')
    assert client.post(f'/api/reports/{ID}/service-appointment', json=data).json() == first.json()
    report = get_store().incident(ID, 'appointment-test')
    assert report['service_appointment'] == first.json()
    assert report['status'] == 'ticket_raised'
    assert len([e for e in get_store().all('complaint_events') if e['event_type']=='service_appointment_booked']) == 1

def test_booking_rejects_other_owner_invalid_centre_and_past_slot():
    setup_report()
    data = payload()
    for patch, code in [({'user_id':'other'},404), ({'centre_id':'unknown'},422), ({'scheduled_start':'2000-01-01T00:00:00Z'},422)]:
        assert client.post(f'/api/reports/{ID}/service-appointment', json={**data, **patch}).status_code == code
    assert not get_store().incident(ID,'appointment-test').get('service_appointment')

def test_resolved_report_cannot_book():
    setup_report(status='resolved')
    assert client.post(f'/api/reports/{ID}/service-appointment', json=payload()).status_code == 409

def test_unsubmitted_report_cannot_book():
    setup_report(status='draft', submitted=False)
    assert client.post(f'/api/reports/{ID}/service-appointment', json=payload()).status_code == 409
