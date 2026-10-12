"""Opt-in live smoke test: one synthetic registration, incident, media and workflow.

Uses real Gemini/GCS/BigQuery and incurs normal project charges. Retains clearly
labelled synthetic records for inspection. Run from backend with PYTHONPATH=.
"""
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from google.cloud import bigquery
from app.main import app
from app import config
from app.services.lifecycle import get_store
from app.services.bigquery import flush_once

def run():
    # This explicit verifier flushes synchronously; do not start a second writer.
    os.environ['PRODUCTLOOP_BIGQUERY_ENABLED'] = '0'
    token = uuid4().hex
    user = 'synthetic-lifecycle-test-' + token
    complaint_id = 'PL-' + token
    serial = 'SYNTHETIC-' + token
    with TestClient(app) as client:
        def post(path, payload):
            response = client.post(path,json=payload)
            response.raise_for_status()
            return response.json()
        post('/api/units/register',{'user_id':user,'serial_number':serial,'product_model':'X500','batch_id':'SYNTHETIC-BATCH'})
        post('/api/incidents',{'user_id':user,'complaint_id':complaint_id,'serial_number':serial,'incident_country':'TEST','incident_city':'Synthetic test only'})
        media = Path(__file__).resolve().parents[2] / 'data/test_media/image1_hair_buildup_under_head.jpg'
        with media.open('rb') as file:
            response = client.post('/api/media/extract',data={'user_id':user,'complaint_id':complaint_id},
                files={'file':(media.name,file,'image/jpeg')})
        response.raise_for_status()
        result = response.json()
        assert result['analysis_mode'] == 'multimodal_gemini', result
        evidence_id = result['evidence_id']
        report = post('/api/reports/confirm',{'user_id':user,'complaint_id':complaint_id,
            'extraction':result['extraction'],'consent_share':False})['report']
        assert post('/api/reports/confirm',{'user_id':user,'complaint_id':complaint_id,
            'extraction':result['extraction']})['report']['report_id'] == complaint_id
        for event in ('not_resolved','create_ticket'):
            post('/api/conversation',{'user_id':user,'report_id':complaint_id,'event':event})
        start = datetime.now(timezone.utc) + timedelta(days=1)
        post(f'/api/reports/{complaint_id}/callback',{'user_id':user,'slot':'Synthetic test callback',
            'scheduled_start':start.isoformat(),'scheduled_end':(start+timedelta(minutes=30)).isoformat(),'time_zone':'Asia/Kolkata'})
        post('/api/conversation',{'user_id':user,'report_id':complaint_id,'event':'resolved'})
    assert get_store().get('evidence',evidence_id)['storage_status'] == 'uploaded'
    while flush_once():
        pass
    client = bigquery.Client(project=config.PROJECT_ID)
    prefix = f'{config.PROJECT_ID}.{config.BQ_DATASET}'
    parameters = [bigquery.ScalarQueryParameter('id','STRING',complaint_id),
        bigquery.ScalarQueryParameter('serial','STRING',serial)]
    query = f"""
      SELECT
        (SELECT COUNT(*) FROM `{prefix}.registered_units` WHERE serial_number=@serial) AS units,
        (SELECT COUNT(*) FROM `{prefix}.complaints` WHERE complaint_id=@id) AS complaints,
        (SELECT COUNT(*) FROM `{prefix}.evidence` WHERE complaint_id=@id AND storage_status='uploaded' AND extraction_status='completed') AS evidence,
        (SELECT COUNT(*) FROM `{prefix}.complaint_events` WHERE complaint_id=@id) AS events,
        (SELECT status FROM `{prefix}.complaints` WHERE complaint_id=@id) AS status
    """
    row = dict(next(iter(client.query(query,job_config=bigquery.QueryJobConfig(query_parameters=parameters)).result())))
    assert row['units'] == row['complaints'] == row['evidence'] == 1, row
    assert row['events'] >= 8 and row['status'] == 'resolved', row
    print(json.dumps({'complaint_id':complaint_id,'evidence_id':evidence_id,'verification':row}))

if __name__ == '__main__':
    run()
