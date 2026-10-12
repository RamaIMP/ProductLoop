import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api import consumer
from app.models.taxonomy import Extraction
from app.services.gemini import ConversationDecision

client = TestClient(app)


def test_unknown_onset_uses_predefined_question(monkeypatch):
    extraction = Extraction(symptoms=['rattling_sound'], confidence=0.9)
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: ConversationDecision(extraction=extraction))
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', lambda _: pytest.fail('No model needed to word this question'))
    result = client.post('/api/conversation', json={'user_id': 'onset-test', 'message': 'It rattles.'}).json()
    assert result['message'] == 'When did this start?'
    assert result['follow_up']['replies'] == ['Today', 'This week', 'Longer ago']


@pytest.mark.parametrize(('label', 'onset'), [('Today', 'today'), ('This week', 'this_week'), ('Longer ago', 'longer')])
def test_button_saves_onset_without_llm(monkeypatch, label, onset):
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: pytest.fail('No LLM needed for button choice'))
    extraction = Extraction(symptoms=['rattling_sound'], context={'persists_after_cleaning': 'yes'}, confidence=0.9)
    result = client.post('/api/conversation', json={'user_id': 'onset-test', 'event': 'onset_selected',
        'message': label, 'extraction': extraction.model_dump(mode='json')}).json()
    assert result['extraction']['context']['onset'] == onset
    assert result['extraction']['context']['persists_after_cleaning'] == 'yes'
    assert result['action'] == 'confirm_report' and result['model'] is None
    assert result['follow_up'] is None


@pytest.mark.parametrize('case', ['known', 'already_asked', 'usage', 'safety', 'unclear'])
def test_question_does_not_interrupt_other_flows(monkeypatch, case):
    extraction = Extraction(symptoms=['burning_smell' if case == 'safety' else 'unclear_description' if case == 'unclear' else 'rattling_sound'],
        user_intent='ask_question' if case == 'usage' else 'report_problem',
        context={'onset': 'today' if case == 'known' else 'unknown'}, confidence=0.9)
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: ConversationDecision(extraction=extraction))
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', lambda _: 'Relevant next response')
    result = client.post('/api/conversation', json={'user_id': 'onset-test', 'message': 'More information',
        'history': [{'role': 'assistant', 'text': 'When did this start?'}] if case == 'already_asked' else []}).json()
    assert result['action'] != 'ask_onset'


def test_invalid_button_cannot_set_onset():
    assert client.post('/api/conversation', json={'user_id': 'onset-test', 'event': 'onset_selected', 'message': 'Yesterday'}).status_code == 409
