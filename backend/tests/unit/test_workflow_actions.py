import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api import consumer
from app.models.taxonomy import Extraction

client = TestClient(app)


def report():
    return client.post('/api/reports/confirm', json={'user_id': 'workflow-test',
        'extraction': Extraction(symptoms=['rattling_sound'], confidence=0.9).model_dump(mode='json')}).json()['report']


@pytest.fixture
def no_llm(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('Workflow actions must not call an LLM')
    for name in ['understand_conversation', 'reply_to_conversation', 'reason_over_retrieval']:
        monkeypatch.setattr(consumer.gemini, name, fail)


def test_ticket_workflow_is_instant_and_idempotent(no_llm):
    saved = report()
    payload = {'user_id': 'workflow-test', 'report_id': saved['report_id']}
    r = client.post('/api/conversation', json={**payload, 'event': 'not_resolved'}).json()
    assert r['mode'] == 'workflow' and r['model'] is None
    assert r['action'] == 'ticket_confirm'
    assert r['report']['status'] == 'unresolved' and 'ticket_id' not in r['report']
    r = client.post('/api/conversation', json={**payload, 'event': 'create_ticket'}).json()
    ticket = r['report']['ticket_id']
    assert ticket in r['message']
    again = client.post('/api/conversation', json={**payload, 'event': 'create_ticket'}).json()
    assert again['report']['ticket_id'] == ticket
    client.post(f"/api/reports/{saved['report_id']}/callback", json={'slot': 'Tomorrow · 10:00 AM'})
    r = client.post('/api/conversation', json={**payload, 'event': 'callback_requested'}).json()
    assert 'Tomorrow · 10:00 AM' in r['message']
    assert 'demo' not in r['message'].lower() and 'no real call' not in r['message']
    r = client.post('/api/conversation', json={**payload, 'event': 'resolved'}).json()
    assert r['report']['status'] == 'resolved' and r['report']['report_id'] == saved['report_id']


@pytest.mark.parametrize('event', ['resolved', 'not_resolved', 'create_ticket', 'callback_requested', 'report_confirmed'])
def test_missing_report_cannot_claim_success(no_llm, event):
    assert client.post('/api/conversation', json={'user_id': 'workflow-test', 'event': event}).status_code == 409


def test_owner_checked_before_workflow_action(no_llm):
    saved = report()
    assert client.post('/api/conversation', json={'user_id': 'other-user',
        'report_id': saved['report_id'], 'event': 'resolved'}).status_code == 404


def test_callback_confirmation_requires_saved_request(no_llm):
    saved = report()
    assert client.post('/api/conversation', json={'user_id': 'workflow-test',
        'report_id': saved['report_id'], 'event': 'callback_requested'}).status_code == 409


@pytest.mark.parametrize('event', ['edit_report', 'add_details'])
def test_detail_controls_do_not_need_models(no_llm, event):
    r = client.post('/api/conversation', json={'user_id': 'workflow-test', 'event': event}).json()
    assert r['mode'] == 'workflow' and r['action'] == event


def test_exact_not_fixed_text_skips_llm_but_mixed_message_does_not(no_llm, monkeypatch):
    saved = report()
    payload = {'user_id': 'workflow-test', 'report_id': saved['report_id']}
    r = client.post('/api/conversation', json={**payload, 'message': 'Still not fixed.'}).json()
    assert r['action'] == 'ticket_confirm'
    seen = []
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda p: seen.append(p) or consumer.gemini.ConversationDecision())
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', lambda _: 'Please describe the new sound.')
    client.post('/api/conversation', json={**payload, 'message': 'Still not fixed, now it rattles.'})
    assert seen


def test_report_confirmation_skips_interpreter_but_uses_retrieval_answer(no_llm, monkeypatch):
    saved = report()
    seen = []
    def answer(**kwargs):
        seen.append(kwargs)
        return consumer.gemini.GroundedReply(message='Supported guidance.', source_ids=[kwargs['retrieval']['chunks'][0]['chunk_id']])
    monkeypatch.setattr(consumer.gemini, 'reason_over_retrieval', answer)
    r = client.post('/api/conversation', json={'user_id': 'workflow-test',
        'report_id': saved['report_id'], 'event': 'report_confirmed'}).json()
    assert r['mode'] == 'gemini_reasoning' and len(seen) == 1
