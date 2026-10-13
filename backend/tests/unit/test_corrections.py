from fastapi.testclient import TestClient
from app.main import app
from app.api import consumer
from app.models.taxonomy import Extraction
from app.services.gemini import ConversationDecision, UserCorrection
from app.services.lifecycle import get_store

client = TestClient(app)


def setup_turn(monkeypatch, message, *, correction=True, symptoms=None):
    previous = Extraction(symptoms=['burning_smell'], confidence=0.9)
    draft = get_store().draft('correction-test')
    cid = draft['report_id']
    get_store().classify(cid, 'correction-test', previous.model_dump(mode='json'),
                         consumer._classification(previous).model_dump(mode='json'))
    decision = ConversationDecision(extraction=Extraction(symptoms=symptoms or ['rattling_sound'], confidence=0.9),
        action='show_guidance', correction=UserCorrection(status='explicit',
            retracted_symptoms=['burning_smell'], quote=message) if correction else None)
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: decision)
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', lambda _: 'Thanks for correcting that. What happens now?')
    monkeypatch.setattr(consumer, 'retrieve_for_report', lambda *a: (_ for _ in ()).throw(AssertionError('No RAG on correction')))
    return cid, decision


def post(cid, message):
    return client.post('/api/conversation', json={'user_id': 'correction-test',
        'complaint_id': cid, 'message': message}).json()


def test_explicit_correction_reclassifies_same_incident_and_records_history(monkeypatch):
    message = 'Sorry, typo. There is no burning smell. It only rattles.'
    cid, _ = setup_turn(monkeypatch, message)
    result = post(cid, message)
    assert result['derived']['safety_flag'] is False
    assert result['extraction']['symptoms'] == ['rattling_sound']
    assert result['action'] == 'ask_onset'
    stored = get_store().incident(cid, 'correction-test')
    assert 'burning' not in stored['complaint_summary']
    events = [e for e in get_store().all('complaint_events') if e['event_type'] == 'complaint_corrected']
    assert events[0]['details']['retracted_symptoms'] == ['burning_smell']


def test_vague_typo_keeps_safety_and_displays_question_even_if_model_claims_explicit(monkeypatch):
    cid, _ = setup_turn(monkeypatch, 'Sorry, typo.')
    result = post(cid, 'Sorry, typo.')
    assert result['derived']['safety_flag'] is True
    assert result['action'] == 'stop_use'
    assert 'What was incorrect' in result['message']
    assert result['response']['priority'] == 'high'


def test_model_clarification_and_unverified_quotes_cannot_remove_hazard(monkeypatch):
    cid, decision = setup_turn(monkeypatch, 'I made an error')
    decision.correction.status = 'needs_clarification'
    assert post(cid, 'I made an error')['derived']['safety_flag'] is True
    decision.correction.status = 'explicit'
    decision.correction.quote = 'Words the user never said'
    assert post(cid, 'I made an error')['derived']['safety_flag'] is True


def test_conflicting_independent_media_is_preserved(monkeypatch):
    message = 'Correction: no burning smell, just rattling.'
    cid, _ = setup_turn(monkeypatch, message)
    store = get_store()
    store.evidence_start('evidence-hazard', cid, 'correction-test', 'shaver.mp4', 'video/mp4')
    store.evidence_update('evidence-hazard', {'extraction_status': 'completed',
        'extracted_symptoms': ['burning_smell']}, 'evidence_analysed')
    result = post(cid, message)
    assert result['derived']['safety_flag'] is True
    assert 'conflicting finding' in result['message']


def test_other_positive_hazard_still_blocks_troubleshooting(monkeypatch):
    message = 'Correction: no burning smell, but it sparks.'
    cid, _ = setup_turn(monkeypatch, message)
    result = post(cid, message)
    assert result['derived']['safety_flag'] is True
    assert 'sparking' in result['extraction']['symptoms']


def test_no_automatic_retraction_when_issue_stops(monkeypatch):
    message = 'The smell stopped now'
    cid, _ = setup_turn(monkeypatch, message, correction=False)
    assert post(cid, message)['derived']['safety_flag'] is True


def test_submitted_report_is_updated_without_changing_ticket_status(monkeypatch):
    message = 'That was a typo. No burning smell, only rattling.'
    cid, _ = setup_turn(monkeypatch, message)
    store = get_store()
    report = store.save_report({**store.incident(cid, 'correction-test'),
        'submitted_at': '2026-10-12T10:00:00Z', 'status': 'ticket_raised', 'ticket_id': 'SR-existing'}, 'report_submitted')
    result = client.post('/api/conversation', json={'user_id': 'correction-test',
        'report_id': cid, 'message': message}).json()
    assert result['report']['derived']['safety_flag'] is False
    assert result['report']['status'] == 'ticket_raised'
    assert result['report']['ticket_id'] == 'SR-existing'
