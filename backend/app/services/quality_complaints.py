"""Read-only quality drill-down. Never return consumer identity or raw complaint text."""
from google.cloud import bigquery
from app.services.bigquery import Writer
from app.rules.dashboard_scope import DASHBOARD_ISSUE_TYPES as ISSUE_TYPES

ELIGIBLE="""c.product_model='X500' AND c.issue_type!='shaving_performance' AND c.counts_as_complaint=TRUE
 AND c.consent_share=TRUE AND c.submitted_at IS NOT NULL
 AND c.user_intent='report_problem' AND COALESCE(c.status,'') NOT IN ('draft','abandoned')"""

def query(w,sql,params):
    return [dict(r) for r in w.client.query(sql,job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter(k,t,v) for k,t,v in params])).result(timeout=60)]

def list_complaints(issue,start,end,region,page,page_size):
    w=Writer()
    params=[('issue','STRING',issue),('start','DATE',start),('end','DATE',end),('region','STRING',region or ''),('limit','INT64',page_size),('offset','INT64',(page-1)*page_size)]
    where=ELIGIBLE+" AND c.issue_type=@issue AND DATE(c.created_at,'Asia/Kolkata') BETWEEN @start AND @end AND (@region='' OR c.region=@region)"
    total=query(w,f'SELECT COUNT(DISTINCT c.complaint_id) total FROM `{w.prefix}.complaints` c WHERE {where}',params)[0]['total']
    rows=query(w,f'''SELECT c.complaint_id,c.created_at,c.complaint_summary,c.symptoms,c.severity,c.safety_flag,c.status,c.batch_reference,c.region,
      (SELECT COUNT(DISTINCT e.evidence_id) FROM `{w.prefix}.evidence` e WHERE e.complaint_id=c.complaint_id AND e.consent_share=TRUE) evidence_count
      FROM `{w.prefix}.complaints` c WHERE {where}
      QUALIFY ROW_NUMBER() OVER(PARTITION BY c.complaint_id ORDER BY c.updated_at DESC)=1
      ORDER BY c.created_at DESC,c.complaint_id LIMIT @limit OFFSET @offset''',params)
    return {'complaints':rows,'total':total,'page':page,'page_size':page_size}

def complaint_detail(complaint_id):
    w=Writer();params=[('id','STRING',complaint_id)]
    rows=query(w,f'''SELECT c.complaint_id,c.created_at,c.updated_at,c.product_model,c.serial_number,c.batch_reference,c.region,
      c.complaint_summary,c.symptoms,c.context,c.issue_type,c.severity,c.safety_flag,c.status,c.guidance_outcome,
      c.submitted_at,c.resolved_at,c.ticket_id,c.callback,c.service_appointment
      FROM `{w.prefix}.complaints` c WHERE {ELIGIBLE} AND c.complaint_id=@id
      ORDER BY c.updated_at DESC LIMIT 1''',params)
    if not rows or rows[0]['issue_type'] not in ISSUE_TYPES: return None
    evidence=query(w,f'''SELECT evidence_id,kind,created_at,extraction_status,extracted_summary,extracted_symptoms,
      extraction_model,storage_status,content_type FROM `{w.prefix}.evidence`
      WHERE complaint_id=@id AND consent_share=TRUE ORDER BY created_at,evidence_id''',params)
    events=query(w,f'''SELECT event_id,occurred_at,event_type,previous_status,new_status,previous_classification,new_classification
      FROM `{w.prefix}.complaint_events` WHERE complaint_id=@id ORDER BY occurred_at,event_id''',params)
    return {'complaint':rows[0],'evidence':evidence,'events':events}

def evidence_media(complaint_id,evidence_id):
    from app import config
    from google.cloud import storage
    w=Writer()
    rows=query(w,f'''SELECT e.gcs_uri,e.content_type FROM `{w.prefix}.evidence` e
      JOIN `{w.prefix}.complaints` c ON c.complaint_id=e.complaint_id
      WHERE {ELIGIBLE} AND c.complaint_id=@id AND e.evidence_id=@evidence AND e.consent_share=TRUE LIMIT 1''',
      [('id','STRING',complaint_id),('evidence','STRING',evidence_id)])
    if not rows: return None
    row=rows[0];prefix=f'gs://{config.MEDIA_BUCKET}/'
    if not config.MEDIA_BUCKET or not (row['gcs_uri'] or '').startswith(prefix): return None
    mime=row['content_type'] or ''
    if mime not in ('image/jpeg','image/png','image/webp','audio/mpeg','audio/wav','audio/x-wav','audio/mp4','audio/ogg','audio/webm','video/mp4','video/webm'): return None
    blob=storage.Client(project=config.PROJECT_ID).bucket(config.MEDIA_BUCKET).blob(row['gcs_uri'][len(prefix):])
    blob.reload(timeout=30)
    if blob.size>30*1024*1024: raise ValueError('Preview supports files up to 30 MB')
    return blob.download_as_bytes(timeout=60,if_generation_match=blob.generation),mime
