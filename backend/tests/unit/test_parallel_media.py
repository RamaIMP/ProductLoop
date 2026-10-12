import asyncio
from io import BytesIO
import pytest
from fastapi import UploadFile, HTTPException
from starlette.datastructures import Headers
from app.api import consumer
from app.services import media_jobs
from app.models.taxonomy import Extraction


def attachment(data=b'photo'):
    return UploadFile(file=BytesIO(data), filename='photo.jpg', headers=Headers({'content-type': 'image/jpeg'}))


def test_analysis_does_not_wait_for_storage(monkeypatch):
    async def scenario():
        release = asyncio.Event()
        async def store(upload):
            await release.wait()
            assert await upload.read() == b'photo'
            return 'gs://private/photo.jpg'
        monkeypatch.setattr(media_jobs, 'store_uploaded_media', store)
        monkeypatch.setattr(consumer, 'extract_from_bytes', lambda *args: Extraction(symptoms=['hair_buildup'], confidence=0.9))
        result = await asyncio.wait_for(consumer.extract_media(attachment(), '', '[]', True, 'test'), 2)
        assert result['analysis_status'] == 'completed'
        assert result['storage']['storage_status'] == 'pending'
        assert result['media']['source'] is None
        with pytest.raises(HTTPException):
            media_jobs.status(result['evidence_id'], 'other-user')
        release.set()
        await media_jobs.finish_uploads()
        assert media_jobs.status(result['evidence_id'], 'test')['storage_status'] == 'uploaded'
    asyncio.run(scenario())


def test_storage_failure_does_not_discard_analysis(monkeypatch):
    async def fail(_):
        raise RuntimeError('storage unavailable')
    async def scenario():
        monkeypatch.setattr(media_jobs, 'store_uploaded_media', fail)
        monkeypatch.setattr(consumer, 'extract_from_bytes', lambda *args: Extraction(symptoms=['hair_buildup'], confidence=0.9))
        result = await consumer.extract_media(attachment(), '', '[]', False, 'test')
        await media_jobs.finish_uploads()
        saved = media_jobs.status(result['evidence_id'], 'test')
        assert saved['storage_status'] == 'failed' and saved['attempts'] == 3
        assert result['analysis_status'] == 'completed'
    asyncio.run(scenario())


def test_analysis_failure_still_saves_media(monkeypatch):
    async def store(_):
        return 'gs://private/photo.jpg'
    def fail(*args):
        raise RuntimeError('model unavailable')
    async def scenario():
        monkeypatch.setattr(media_jobs, 'store_uploaded_media', store)
        monkeypatch.setattr(consumer, 'extract_from_bytes', fail)
        result = await consumer.extract_media(attachment(), '', '[]', False, 'test')
        await media_jobs.finish_uploads()
        assert result['analysis_status'] == 'failed'
        assert media_jobs.status(result['evidence_id'], 'test')['storage_status'] == 'uploaded'
    asyncio.run(scenario())


@pytest.mark.parametrize('data', [b'', b'x' * (15 * 1024 * 1024 + 1)], ids=['empty', 'oversized'])
def test_size_limits(data):
    with pytest.raises(HTTPException) as error:
        asyncio.run(consumer.extract_media(attachment(data), '', '[]', False, 'test'))
    assert error.value.status_code == 413
