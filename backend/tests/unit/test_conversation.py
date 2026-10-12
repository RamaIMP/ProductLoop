from fastapi.testclient import TestClient

from app.main import app
from app.api import consumer
from app.models.taxonomy import Extraction
from app.services.gemini import ConversationDecision

client = TestClient(app)


def test_text_interpretation_disables_thinking(monkeypatch):
    from types import SimpleNamespace
    from app.services import gemini
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text='{"action":"continue","message":"What happens when you turn it on?"}')
    monkeypatch.setattr(gemini, 'client', lambda: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    gemini.understand_conversation({'message': 'My shaver is acting weird.'})
    assert len(calls) == 1
    assert calls[0]['config'].thinking_config.thinking_budget == 0


def test_greeting_is_instant_without_calling_llm_or_creating_report(monkeypatch):
    seen = []
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda payload: seen.append(payload.copy()) or ConversationDecision())
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', lambda payload: 'Hello! How can I help with your shaver?')
    result = client.post('/api/conversation', json={'user_id': 'chat-test', 'message': 'hi',
        'history': [{'role': 'assistant', 'text': 'Welcome!'}]}).json()
    assert not seen
    assert result['message'].startswith('Hi!')
    assert result['extraction'] is None and result['report'] is None
    assert result['mode'] == 'instant_greeting'


def test_chat_open_returns_requested_welcome_without_model(monkeypatch):
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: (_ for _ in ()).throw(AssertionError('No model needed')))
    result = client.post('/api/conversation', json={'user_id': 'chat-test', 'message': '', 'event': 'session_start'}).json()
    assert result['message'] == 'Welcome to ProductLoop X500 support! How can I help you today? Feel free to describe your issue or send a picture or video.'


def test_greeting_prefix_with_fault_is_not_fast_pathed(monkeypatch):
    seen = []
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda p: seen.append(p) or ConversationDecision())
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', lambda _: 'When did the charging problem start?')
    result = client.post('/api/conversation', json={'user_id': 'chat-test', 'message': 'Hi, my shaver will not charge'}).json()
    assert seen
    assert result['mode'] == 'gemini_conversation'


def test_normal_followup_uses_original_two_stage_flow(monkeypatch):
    calls = []
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: calls.append('interpret') or ConversationDecision())
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', lambda _: calls.append('reply') or 'What happens when you turn it on?')
    result = client.post('/api/conversation', json={'user_id': 'chat-test', 'message': 'My shaver is acting weird'}).json()
    assert result['message'] == 'What happens when you turn it on?'
    assert calls == ['interpret', 'reply']


def test_followup_preserves_media_symptoms_and_updates_context(monkeypatch):
    previous = Extraction(symptoms=['hair_buildup'], confidence=0.9)
    updated = Extraction(symptoms=['pulling_hair'], context={'onset': 'today'}, confidence=0.9)
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: ConversationDecision(extraction=updated, action='confirm_report'))
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', lambda _: 'Please check these details.')
    result = client.post('/api/conversation', json={'user_id': 'chat-test', 'message': 'Today, and it pulls my hair',
        'extraction': previous.model_dump(mode='json')}).json()
    assert set(result['extraction']['symptoms']) == {'hair_buildup', 'pulling_hair'}
    assert result['extraction']['context']['onset'] == 'today'


def test_llm_failure_is_an_error_not_a_canned_conversation(monkeypatch):
    def fail(_):
        raise RuntimeError('offline')
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', fail)
    assert client.post('/api/conversation', json={'user_id': 'chat-test', 'message': 'My shaver is acting weird'}).status_code == 503
    result = client.post('/api/conversation', json={'user_id': 'chat-test', 'message': 'My shaver burned'}).json()
    assert result['action'] == 'stop_use'
    assert result['mode'] == 'safety_guardrail'


def test_safety_overrides_llm_suggestion_and_excludes_troubleshooting(monkeypatch):
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: ConversationDecision(action='show_guidance'))
    seen = []
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', lambda payload: seen.append(payload) or 'Please stop using it.')
    result = client.post('/api/conversation', json={'user_id': 'chat-test', 'message': 'My shaver burned'}).json()
    assert result['action'] == 'stop_use'
    assert seen == []  # Safety advice is deterministic, without a second model call.
    assert result['derived']['safety_flag'] is True
    assert 'charging' in ' '.join(result['response']['steps'])


def test_conversational_outcomes_update_same_report_and_keep_ticket_id(monkeypatch):
    extraction = Extraction(symptoms=['rattling_sound'], confidence=0.9)
    created = client.post('/api/reports/confirm', json={'user_id': 'chat-outcome',
        'extraction': extraction.model_dump(mode='json')}).json()['report']
    action = ['raise_ticket']
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: ConversationDecision(extraction=extraction, action=action[0]))
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', lambda payload: payload['saved_report']['status'])
    payload = {'user_id': 'chat-outcome', 'report_id': created['report_id'], 'message': 'Please create a ticket'}
    first = client.post('/api/conversation', json=payload).json()
    second = client.post('/api/conversation', json=payload).json()
    assert first['report']['ticket_id'] == second['report']['ticket_id']
    assert second['message'] == 'ticket_raised'
    action[0] = 'resolved'
    result = client.post('/api/conversation', json={**payload, 'message': 'It is fixed now'}).json()
    assert result['report']['status'] == 'resolved'
    assert result['report']['report_id'] == created['report_id']
    assert client.post('/api/conversation', json={**payload, 'user_id': 'someone-else'}).status_code == 404


def test_guidance_uses_separate_reasoner_and_returns_its_answer_directly(monkeypatch):
    from app.services.gemini import GroundedReply
    extraction = Extraction(symptoms=['hair_buildup'], confidence=0.9)
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: ConversationDecision(extraction=extraction, action='show_guidance'))
    def chat_must_not_rewrite(_):
        raise AssertionError('The chat model must not rewrite the reasoning answer')
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', chat_must_not_rewrite)
    seen = []
    def reason(**kwargs):
        seen.append(kwargs)
        return GroundedReply(message='Grounded model answer', source_ids=[kwargs['retrieval']['chunks'][0]['chunk_id']])
    monkeypatch.setattr(consumer.gemini, 'reason_over_retrieval', reason)
    response = client.post('/api/conversation', json={'user_id': 'reason-test', 'message': 'How do I remove trapped hair?'}).json()
    assert response['message'] == 'Grounded model answer'
    assert response['mode'] == 'gemini_reasoning'
    assert response['retrieval_mode'] == 'development_mock'
    assert response['sources']
    assert seen[0]['retrieval']['query'].find('trapped hair') >= 0
    assert 'text' in seen[0]['retrieval']['chunks'][0]


def test_reasoning_call_uses_dedicated_model_and_text_only(monkeypatch):
    import json
    from types import SimpleNamespace
    from app.services import gemini
    seen = []
    def generate(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(text='{"message":"Please contact support; the retrieved knowledge is insufficient.","source_ids":[]}')
    monkeypatch.setattr(gemini, 'client', lambda: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    monkeypatch.setattr(gemini.config, 'MODEL_REASON', 'dedicated-reasoner')
    gemini.reason_over_retrieval(message='Help', history=[], extraction=Extraction(symptoms=['hair_buildup'], confidence=0.9),
        derived={'safety_flag': False}, retrieval={'query': 'hair buildup', 'chunks': []})
    assert seen[0]['model'] == 'dedicated-reasoner'
    assert isinstance(seen[0]['contents'], str)
    assert json.loads(seen[0]['contents'])['user_message'] == 'Help'
    assert len(seen) == 1


def test_negated_hazards_do_not_inject_false_symptoms(monkeypatch):
    extraction = Extraction(symptoms=['not_charging'], confidence=0.9)
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: ConversationDecision(extraction=extraction, action='confirm_report'))
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', lambda _: 'Please check your charging report.')
    result = client.post('/api/conversation', json={'user_id': 'negation-test',
        'message': 'It won’t charge. There is no heat, smoke, or burning smell.'}).json()
    assert result['extraction']['symptoms'] == ['not_charging']
    assert result['derived'] == {'issue_type': 'power_and_charging', 'severity': 'medium', 'safety_flag': False}
    assert result['action'] == 'ask_onset'  # Unknown start time is now collected before review.
    # Earlier positive evidence must not be erased by a later denial.
    previous = Extraction(symptoms=['burning_smell'], confidence=0.9)
    result = client.post('/api/conversation', json={'user_id': 'negation-test',
        'message': 'There is no heat, smoke, or burning smell now.',
        'extraction': previous.model_dump(mode='json')}).json()
    assert result['derived']['safety_flag'] is True
    assert result['action'] == 'stop_use'
