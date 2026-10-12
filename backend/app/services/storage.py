"""Private media storage for development and Cloud Storage deployments."""
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError
from google.cloud import storage

from app import config


async def store_uploaded_media(upload: UploadFile) -> str:
    """Archive one attachment and return a ``gs://`` or local storage path.

    A private Cloud Storage bucket is used when ``GCS_MEDIA_BUCKET`` is set.
    Local development writes to the OS temp directory instead, never to Git.
    """
    original_name = Path(upload.filename or "attachment").name
    # Keep the extension for Gemini MIME detection, not potentially personal filenames.
    object_name = f"uploads/{uuid4().hex}{Path(original_name).suffix.lower()}"
    if config.MEDIA_BUCKET:
        def upload_private():
            bucket = storage.Client(project=config.PROJECT_ID).bucket(config.MEDIA_BUCKET)
            blob = bucket.blob(object_name)
            blob.cache_control = 'private, no-store'
            blob.upload_from_file(upload.file, rewind=True,
                content_type=upload.content_type or 'application/octet-stream',
                if_generation_match=0, timeout=60)
        try:
            # Cloud I/O must not block the API event loop or copy the whole video into RAM.
            await run_in_threadpool(upload_private)
        except (GoogleAPIError, GoogleAuthError) as exc:
            # Do not silently fall back to local storage when cloud upload fails.
            raise HTTPException(status_code=503, detail='Cloud media upload failed. Please retry the upload.') from exc
        return f"gs://{config.MEDIA_BUCKET}/{object_name}"

    data = await upload.read()
    directory = Path(tempfile.gettempdir()) / "productloop-media"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / Path(object_name).name
    destination.write_bytes(data)
    return str(destination)
