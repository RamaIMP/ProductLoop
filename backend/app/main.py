from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.media_jobs import finish_uploads
from fastapi.middleware.cors import CORSMiddleware

from app.api.consumer import router as consumer_router
from app.api.consumer import _REPORTS
from app.api.lifecycle import router as lifecycle_router
from app.api.dashboard import router as dashboard_router
from app.api.manufacturing import router as manufacturing_router
from app.services.lifecycle import get_store
from app.services.bigquery import start_worker
from app.services.analysis_store import start_analysis_worker

@asynccontextmanager
async def lifespan(app):
    store = get_store()
    store.recover_interrupted()
    _REPORTS.update({r['report_id']:r for r in store.all('complaints') if r.get('submitted_at') or r.get('legacy_confirmed')})
    stop, thread = start_worker()
    analysis_stop, analysis_thread = start_analysis_worker()
    yield
    await finish_uploads()
    stop.set()
    analysis_stop.set()


app = FastAPI(title="ProductLoop API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(consumer_router)
app.include_router(lifecycle_router)
app.include_router(dashboard_router)
app.include_router(manufacturing_router)


@app.get("/health")
def health():
    return {"status": "ok"}
