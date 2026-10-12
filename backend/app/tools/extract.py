"""Reads the media once with Gemini and returns the complaint record. Called by the API before the chat agent runs."""
import mimetypes
from pathlib import Path

from google.genai import types

from app.models.taxonomy import Extraction
from app.services import gemini

_EXTRA_MIME = {".m4a": "audio/mp4", ".mp4": "video/mp4", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".wav": "audio/wav", ".mp3": "audio/mpeg"}


def guess_mime(source: str) -> str:
    ext = Path(source).suffix.lower()
    return _EXTRA_MIME.get(ext) or mimetypes.guess_type(source)[0] or "application/octet-stream"


def media_part(source: str) -> types.Part:
    """gs:// links are read by Gemini directly from Cloud Storage; local paths (tests) are sent as bytes."""
    mime = guess_mime(source)
    if source.startswith("gs://"):
        return types.Part.from_uri(file_uri=source, mime_type=mime)
    return types.Part.from_bytes(data=Path(source).read_bytes(), mime_type=mime)


def extract_from_media(sources: list[str], message: str = "") -> Extraction:
    """One call for all attached files plus any typed text."""
    return gemini.extract(message, media=[media_part(s) for s in sources])


def extract_from_bytes(data: bytes, mime_type: str, message: str = '') -> Extraction:
    """Direct analysis path, independent of the archival Cloud Storage upload."""
    return gemini.extract(message, media=[types.Part.from_bytes(data=data, mime_type=mime_type)])
