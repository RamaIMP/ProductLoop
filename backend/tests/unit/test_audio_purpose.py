import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api import consumer
from app.models.taxonomy import Extraction

@pytest.mark.parametrize('purpose,expected', [('spoken_complaint','Do not treat their voice as a shaver noise'),('device_sound','device-sound recording')])
def test_audio_purpose_reaches_extraction(monkeypatch,purpose,expected):
    seen=[]
    async def store(_): return 'gs://test/voice.webm'
    monkeypatch.setattr(consumer.media_jobs,'store_uploaded_media',store)
    def extract(data,mime,prompt):
        seen.append((mime,prompt))
        return Extraction(symptoms=['not_charging'],confidence=.9)
    monkeypatch.setattr(consumer,'extract_from_bytes',extract)
    with TestClient(app) as client:
        response=client.post('/api/media/extract',data={'audio_purpose':purpose},files={'file':('voice.webm',b'audio','audio/webm')})
    assert response.status_code==200
    assert seen[0][0]=='audio/webm'
    assert expected in seen[0][1]

def test_invalid_purpose_and_non_audio_are_rejected():
    client=TestClient(app)
    for purpose,mime in [('unknown','audio/webm'),('spoken_complaint','image/jpeg')]:
        response=client.post('/api/media/extract',data={'audio_purpose':purpose},files={'file':('file',b'data',mime)})
        assert response.status_code==422
