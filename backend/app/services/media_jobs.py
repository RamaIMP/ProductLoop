"""Development background uploads with durable evidence metadata and BigQuery outbox."""
import asyncio
from io import BytesIO
from time import monotonic
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from app.services.storage import store_uploaded_media
from app.services.lifecycle import get_store, now as utc_now

JOBS = {}
TASKS = set()


def status(evidence_id, user_id):
    job = JOBS.get(evidence_id)
    if not job or job['user_id'] != user_id:
        record = get_store().get('evidence',evidence_id)
        if not record or record['consumer_id'] != user_id:
            raise HTTPException(status_code=404, detail='Upload status not found.')
        return {'evidence_id':evidence_id, 'storage_status':record['storage_status'],
            'storage_uri':record.get('gcs_uri'), 'error':record.get('storage_error'),
            'record_status':'durably_queued', 'elapsed_ms':0}
    return {**{key: value for key, value in job.items() if key != 'started'}, 'record_status':'durably_queued'}


def start_upload(data, filename, content_type, user_id, complaint_id=None, evidence_id=None):
    now = monotonic()
    for key, job in list(JOBS.items()):
        if job['storage_status'] != 'pending' and now - job['started'] > 3600:
            del JOBS[key]
    if len(TASKS) >= 8:
        raise HTTPException(status_code=429, detail='Too many pending media uploads. Please retry shortly.')
    evidence_id = evidence_id or f'ev_{uuid4().hex}'
    if get_store().get('evidence',evidence_id):
        raise HTTPException(409,'This upload is already processing. Check its status before retrying.')
    complaint_id = get_store().draft(user_id,complaint_id)['report_id']
    get_store().evidence_start(evidence_id,complaint_id,user_id,filename,content_type)
    job = JOBS[evidence_id] = {'evidence_id': evidence_id, 'user_id': user_id,
        'storage_status': 'pending', 'storage_uri': None, 'attempts': 0,
        'elapsed_ms': 0, 'started': now, 'record_status': 'durably_queued'}

    async def worker():
        # Independent stream: request teardown and Gemini never share its cursor.
        upload = UploadFile(file=BytesIO(data), filename=filename,
                            headers=Headers({'content-type': content_type}))
        try:
            for attempt in range(3):
                job['attempts'] = attempt + 1
                try:
                    await upload.seek(0)
                    uri = await store_uploaded_media(upload)
                    job.update(storage_status='uploaded', storage_uri=uri)
                    break
                except Exception:
                    if attempt == 2:
                        job.update(storage_status='failed', error='Evidence was not saved. Please retry the upload.')
                    else:
                        await asyncio.sleep(attempt + 1)
        except asyncio.CancelledError:
            job.update(storage_status='failed', error='Upload interrupted. Please retry the upload.')
            raise
        finally:
            job['elapsed_ms'] = round((monotonic() - now) * 1000, 1)
            get_store().evidence_update(evidence_id, {
                'storage_status':job['storage_status'], 'gcs_uri':job['storage_uri'] if (job['storage_uri'] or '').startswith('gs://') else None,
                'stored_at':utc_now() if job['storage_status'] == 'uploaded' else None,
                'storage_error':job.get('error')},
                'evidence_stored' if job['storage_status'] == 'uploaded' else 'storage_failed')
            await upload.close()

    task = asyncio.create_task(worker())
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)
    return evidence_id


async def finish_uploads():
    if TASKS:
        await asyncio.gather(*list(TASKS), return_exceptions=True)
