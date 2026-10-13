from fastapi import FastAPI, Depends
import os
from app.auth import auth_mode, identity, consumer_access, staff_access
from contextlib import asynccontextmanager
from app.services.media_jobs import finish_uploads
from fastapi.middleware.cors import CORSMiddleware

from app.api.consumer import router as consumer_router
from app.api.lifecycle import router as lifecycle_router
from app.api.dashboard import router as dashboard_router
from app.api.manufacturing import router as manufacturing_router
from app.services.lifecycle import get_store
from app.services.bigquery import start_worker
from app.services.analysis_store import start_analysis_worker

@asynccontextmanager
async def lifespan(app):
    auth_mode()
    store = get_store()
    store.recover_interrupted()
    stop, thread = start_worker()
    analysis_stop, analysis_thread = start_analysis_worker()
    yield
    await finish_uploads()
    stop.set()
    analysis_stop.set()


app = FastAPI(title="ProductLoop API", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[s.strip() for s in os.getenv('PRODUCTLOOP_CORS_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174').split(',') if s.strip() and s.strip() != '*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(consumer_router, dependencies=[Depends(consumer_access)])
app.include_router(lifecycle_router, dependencies=[Depends(consumer_access)])
app.include_router(dashboard_router, dependencies=[Depends(staff_access)])
app.include_router(manufacturing_router, dependencies=[Depends(staff_access)])


@app.middleware('http')
async def private_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.get('/api/auth/me')
def me(user=Depends(identity)):
    return user


@app.get("/health")
def health():
    return {"status": "ok"}
