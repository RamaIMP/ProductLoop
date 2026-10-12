import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api import consumer
from app.services.greetings import greeting_reply

CASES = json.loads((Path(__file__).resolve().parents[3] / 'shared/greeting-cases.json').read_text())


@pytest.mark.parametrize('message', CASES['greetings'])
def test_greetings_bypass_model(monkeypatch, message):
    def unexpected(_):
        raise AssertionError('Greeting must not call Gemini')
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', unexpected)
    result = TestClient(app).post('/api/conversation', json={'user_id': 'greeting-test', 'message': message})
    assert result.status_code == 200
    assert result.json()['mode'] == 'instant_greeting'
    assert result.json()['message'] == greeting_reply(message)


@pytest.mark.parametrize('message', CASES['not_greetings'])
def test_mixed_or_substantive_messages_are_not_greetings(message):
    assert greeting_reply(message) is None
