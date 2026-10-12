"""M0 check: one Gemini reply from your laptop. Run from the repo root after `gcloud auth application-default login`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app import config  # noqa: E402
from google import genai  # noqa: E402

model = config.MODEL_CHAT or config.MODEL_EXTRACT
if not (config.PROJECT_ID and model):
    raise SystemExit("Set GOOGLE_CLOUD_PROJECT and GEMINI_MODEL_CHAT, in .env or backend/app/dev_defaults.json.")
client = genai.Client(vertexai=True, project=config.PROJECT_ID, location=config.LOCATION)
print(client.models.generate_content(model=model, contents="Reply with one short sentence confirming you can hear me.").text)
