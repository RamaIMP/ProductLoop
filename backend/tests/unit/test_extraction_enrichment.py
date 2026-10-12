import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.taxonomy import Extraction
from app.services import gemini


def extraction(**updates):
    return dict(symptoms=['not_charging'], confidence=.9,
                complaint_summary='Will not charge; no smoke reported.',
                retrieval_query='X500 will not charge. No smoke reported. Charging guidance.', **updates)


def test_legacy_extraction_still_valid():
    parsed = Extraction(symptoms=['rattling_sound'], confidence=.8)
    assert parsed.retrieval_query is None
    assert parsed.media_findings is None


@pytest.mark.parametrize('mime_type', ['image/jpeg', 'audio/wav', 'video/mp4'])
def test_media_extraction_disables_thinking(monkeypatch, mime_type):
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(extraction()))
    monkeypatch.setattr(gemini, 'client', lambda: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    part = gemini.types.Part.from_bytes(data=b'test-media', mime_type=mime_type)
    gemini.extract('Check this file', media=[part])
    assert len(calls) == 1
    assert calls[0]['config'].thinking_config.thinking_budget == 0
    assert calls[0]['contents'][0].parts[0].inline_data.mime_type == mime_type


def test_conversation_returns_enrichment_without_an_extra_call(monkeypatch):
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=json.dumps({'extraction': extraction(), 'action':'show_guidance'}))
    monkeypatch.setattr(gemini, 'client', lambda: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    result = gemini.understand_conversation({'message':'It will not charge; no smoke.'})
    assert len(calls) == 1
    assert result.extraction.complaint_summary == 'Will not charge; no smoke reported.'
    assert 'No smoke' in result.extraction.retrieval_query
    assert result.action == 'show_guidance'


def test_media_observations_are_separate_and_text_cannot_invent_them():
    parsed = Extraction(**extraction(media_findings={'summary':'Charging indicator is dark.',
        'symptoms':['led_not_working'], 'limitations':['Cannot determine battery condition from the image.'],
        'confidence':.7}))
    assert gemini.validate_enrichment(parsed, has_media=True).media_findings.confidence == .7
    assert gemini.validate_enrichment(parsed, has_media=False).media_findings is None


@pytest.mark.parametrize('symptom', ['burning_smell', 'unclear_description'])
def test_hazard_and_unclear_output_cannot_request_retrieval(symptom):
    parsed = Extraction(symptoms=[symptom], confidence=.8, retrieval_query='Try troubleshooting')
    assert gemini.validate_enrichment(parsed).retrieval_query is None


def test_blank_and_invalid_enrichment():
    assert Extraction(symptoms=['not_charging'],confidence=.8,retrieval_query='  ').retrieval_query is None
    with pytest.raises(ValidationError):
        Extraction(**extraction(media_findings={'summary':'Observed','symptoms':['invented'], 'confidence':.8}))


def test_spoken_vague_problem_is_not_unclear_audio_and_uses_one_call(monkeypatch):
    calls=[]
    speech={'status':'understood','intent':'vague_problem','message':'I have an issue with my shaver','reply':'What is happening with your shaver?'}
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=json.dumps({'symptoms':['unclear_description'],'confidence':.9,'speech':speech}))
    monkeypatch.setattr(gemini,'client',lambda:SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    part=gemini.types.Part.from_bytes(data=b'voice',mime_type='audio/webm')
    result=gemini.extract('This is a spoken complaint recording',media=[part])
    assert result.speech.status=='understood'
    assert result.speech.intent=='vague_problem'
    assert result.retrieval_query is None
    assert len(calls)==1
    assert calls[0]['config'].thinking_config.thinking_budget==0
    assert 'not unclear audio' in calls[0]['config'].system_instruction
    assert gemini.validate_enrichment(result,has_media=False).speech is None
