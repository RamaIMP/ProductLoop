from fastapi.testclient import TestClient
from app.main import app
from app.api import consumer
from app.models.taxonomy import Extraction
from app.services.gemini import ConversationDecision, GroundedReply

client = TestClient(app)


def test_media_trace_shows_storage_uri_extraction_and_classification(monkeypatch):
    uri = 'gs://private-bucket/uploads/test.jpg'
    async def store(_):
        return uri
    seen = []
    def extract(data, mime, prompt):
        seen.append((data, mime))
        return Extraction(symptoms=['hair_buildup'], confidence=0.9)
    monkeypatch.setattr(consumer.media_jobs, 'store_uploaded_media', store)
    monkeypatch.setattr(consumer, 'extract_from_bytes', extract)
    response = client.post('/api/media/extract', data={'debug': 'true', 'prior_symptoms_json': '["rattling_sound"]'},
        files={'file': ('test.jpg', b'test', 'image/jpeg')})
    stages = response.json()['debug']['stages']
    assert seen == [(b'test', 'image/jpeg')]
    assert stages[0]['output']['storage_status'] == 'pending'
    assert stages[1]['output']['input_mode'] == 'inline_bytes'
    assert stages[1]['output']['findings']['symptoms'] == ['hair_buildup']
    assert stages[2]['output']['extraction']['symptoms'] == ['rattling_sound', 'hair_buildup']
    assert all(stage['elapsed_ms'] >= 0 for stage in stages)


def test_debug_trace_includes_section_outputs_without_extra_calls(monkeypatch):
    calls = []
    extraction = Extraction(symptoms=['hair_buildup'], user_intent='ask_question', confidence=0.9)
    def understand(_):
        calls.append('interpret')
        return ConversationDecision(extraction=extraction, action='show_guidance')
    def answer(**kwargs):
        calls.append('answer')
        return GroundedReply(message='Rinse each blade unit.', source_ids=[kwargs['retrieval']['chunks'][0]['chunk_id']])
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', understand)
    monkeypatch.setattr(consumer.gemini, 'reason_over_retrieval', answer)
    r = client.post('/api/conversation', json={'user_id': 'debug-test', 'message': 'How do I clean it?', 'debug': True}).json()
    stages = r['debug']['stages']
    assert len(stages) == 4 and calls == ['interpret', 'answer']
    assert stages[0]['output']['action'] == 'show_guidance'
    assert stages[1]['output']['derived']['issue_type'] == 'cleaning_and_maintenance'
    assert stages[2]['output']['query'] and stages[2]['output']['chunks']
    assert stages[3]['output']['message'] == r['message']
    assert all(s['elapsed_ms'] >= 0 for s in stages)


def test_debug_off_omits_trace(monkeypatch):
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: ConversationDecision())
    monkeypatch.setattr(consumer.gemini, 'reply_to_conversation', lambda _: 'Please describe the issue.')
    r = client.post('/api/conversation', json={'user_id': 'debug-test', 'message': 'Help'}).json()
    assert 'debug' not in r


def test_onset_template_retains_interpretation_trace(monkeypatch):
    extraction = Extraction(symptoms=['rattling_sound'], confidence=0.9)
    monkeypatch.setattr(consumer.gemini, 'understand_conversation', lambda _: ConversationDecision(extraction=extraction))
    r = client.post('/api/conversation', json={'user_id': 'debug-test', 'message': 'It rattles.', 'debug': True}).json()
    assert r['mode'] == 'workflow'
    assert len(r['debug']['stages']) == 2
    assert r['debug']['stages'][0]['model'] is not None
