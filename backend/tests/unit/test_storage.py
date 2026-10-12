import asyncio
from io import BytesIO
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from google.api_core.exceptions import Forbidden
from app.services import storage
from app.tools.extract import media_part


def upload():
    return UploadFile(file=BytesIO(b'example-image'), filename='private-customer-name.JPG',
                      headers=Headers({'content-type': 'image/jpeg'}))


def test_private_upload_uses_gcs_stream_and_unique_nonpersonal_name(monkeypatch):
    blob = Mock()
    bucket = Mock()
    bucket.blob.return_value = blob
    client = Mock()
    client.bucket.return_value = bucket
    monkeypatch.setattr(storage.config, 'MEDIA_BUCKET', 'private-test-bucket')
    monkeypatch.setattr(storage.storage, 'Client', lambda **_: client)
    result = asyncio.run(storage.store_uploaded_media(upload()))
    assert result.startswith('gs://private-test-bucket/uploads/') and result.endswith('.jpg')
    assert 'private-customer-name' not in result
    client.bucket.assert_called_once_with('private-test-bucket')
    assert blob.cache_control == 'private, no-store'
    kwargs = blob.upload_from_file.call_args.kwargs
    assert kwargs['if_generation_match'] == 0 and kwargs['rewind'] is True
    assert kwargs['content_type'] == 'image/jpeg'
    blob.make_public.assert_not_called()


def test_cloud_failure_does_not_fall_back_to_local_storage(monkeypatch):
    monkeypatch.setattr(storage.config, 'MEDIA_BUCKET', 'private-test-bucket')
    def fail(**_):
        raise Forbidden('private diagnostic detail')
    monkeypatch.setattr(storage.storage, 'Client', fail)
    with pytest.raises(HTTPException) as error:
        asyncio.run(storage.store_uploaded_media(upload()))
    assert error.value.status_code == 503
    assert 'private diagnostic' not in error.value.detail


def test_gemini_receives_private_uri_not_media_bytes():
    part = media_part('gs://private-test-bucket/uploads/example.jpg')
    assert part.file_data.file_uri == 'gs://private-test-bucket/uploads/example.jpg'
    assert part.file_data.mime_type == 'image/jpeg'
    assert part.inline_data is None
