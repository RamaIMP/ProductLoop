import json
from types import SimpleNamespace

import pytest

from app.models.taxonomy import Extraction
from app.services import gemini


def fake_model(monkeypatch, responses):
    pending = iter(responses)
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(next(pending)))
    monkeypatch.setattr(gemini, 'client', lambda: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    return calls


def reason(chunks=None, safety=False):
    return gemini.reason_over_retrieval(
        message='Can I use a third-party replacement head?', history=[],
        extraction=Extraction(symptoms=['blade_replacement_due'], confidence=0.9),
        derived={'safety_flag': safety}, retrieval={'query': 'replacement head', 'chunks': chunks or []})


CLEANING = {'chunk_id': 'clean', 'title': 'Cleaning', 'text': 'Rinse each blade unit.'}
GAP = {'message': 'I do not have verified compatibility information. Please contact customer support.', 'source_ids': []}


@pytest.mark.parametrize('chunks', [[], [CLEANING]])
def test_gap_reply_uses_one_call(monkeypatch, chunks):
    calls = fake_model(monkeypatch, [GAP])
    assert reason(chunks).model_dump() == GAP
    assert len(calls) == 1


@pytest.mark.parametrize('bad', [
    {'message': 'Rinse the blades.', 'source_ids': ['invented']},
    {'message': '', 'source_ids': []},
])
def test_invalid_output_fails_without_extra_model_calls(monkeypatch, bad):
    calls = fake_model(monkeypatch, [bad])
    with pytest.raises(ValueError):
        reason([CLEANING])
    assert len(calls) == 1


def test_supported_answer_preserved_in_one_call(monkeypatch):
    answer = {'message': 'Rinse each blade unit.', 'source_ids': ['clean']}
    calls = fake_model(monkeypatch, [answer])
    assert reason([CLEANING]).model_dump() == answer
    assert len(calls) == 1


def test_safety_bypasses_reasoning(monkeypatch):
    calls = fake_model(monkeypatch, [])
    with pytest.raises(ValueError, match='Unsafe'):
        reason([CLEANING], safety=True)
    assert not calls


def test_cleaning_prerequisite_survives_model_summarisation(monkeypatch):
    prerequisite = 'Before cleaning, switch off the shaver and disconnect it from charging.'
    chunk = {'chunk_id':'x500_man_cleaning','title':'Cleaning','text':prerequisite+' Remove the head.'}
    fake_model(monkeypatch,[{'message':'Remove the head.', 'source_ids':['x500_man_cleaning']}])
    assert reason([chunk]).message.startswith(prerequisite)


def test_cleaning_precaution_is_not_repeated_when_already_in_opening(monkeypatch):
    prerequisite = 'Before cleaning, switch off the shaver and disconnect it from charging.'
    message = 'To clean the head, first switch off the shaver and disconnect it from charging. Remove the head.'
    fake_model(monkeypatch,[{'message':message,'source_ids':['x500_man_cleaning']}])
    assert reason([{'chunk_id':'x500_man_cleaning','title':'Cleaning','text':prerequisite}]).message == message
