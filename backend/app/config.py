"""Settings. Order of precedence: real environment variables, then .env (local overrides), then dev_defaults.json.
Everything here is non-secret; Google credentials come from the gcloud login, never from files in the repo.
Set PRODUCTLOOP_SKIP_DOTENV=1 to ignore .env (tests, automation)."""
import json
import os
from pathlib import Path

if not os.getenv("PRODUCTLOOP_SKIP_DOTENV"):
    from dotenv import load_dotenv

    load_dotenv()

_DEFAULTS = json.loads((Path(__file__).with_name("dev_defaults.json")).read_text())


def _get(name: str) -> str:
    return os.getenv(name) or _DEFAULTS.get(name, "")


PROJECT_ID = _get("GOOGLE_CLOUD_PROJECT")
LOCATION = _get("GOOGLE_CLOUD_LOCATION")
BQ_DATASET = _get("BQ_DATASET")
MEDIA_BUCKET = _get("GCS_MEDIA_BUCKET")
SESSION_BACKEND = _get("SESSION_BACKEND")
MODEL_EXTRACT = _get("GEMINI_MODEL_EXTRACT")
MODEL_CHAT = _get("GEMINI_MODEL_CHAT")
MODEL_REASON = _get("GEMINI_MODEL_REASON")
EMBEDDING_MODEL = _get("EMBEDDING_MODEL")
RAG_MODE = _get('PRODUCTLOOP_RAG_MODE') or 'live'
RAG_ALLOW_DRAFT = _get('PRODUCTLOOP_RAG_ALLOW_DRAFT') or '0'

# ADK and the Google client read these from the process environment.
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", LOCATION)
