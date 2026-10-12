import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("PRODUCTLOOP_SKIP_DOTENV", "1")  # tests never read .env
os.environ['PRODUCTLOOP_RAG_MODE'] = 'mock'  # unit tests never call live retrieval

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(autouse=True)
def isolated_lifecycle(monkeypatch):
    from app.services import lifecycle
    store = lifecycle.LifecycleStore(':memory:')
    monkeypatch.setattr(lifecycle, '_store', store)
    monkeypatch.setenv('PRODUCTLOOP_BIGQUERY_ENABLED', '0')
    yield
    store.db.close()


@pytest.fixture(scope="session")
def complaints():
    return json.loads((DATA / "x500_complaints_v2.json").read_text())["complaints"]


@pytest.fixture(scope="session")
def taxonomy():
    return json.loads((DATA / "taxonomy_v2.json").read_text())
