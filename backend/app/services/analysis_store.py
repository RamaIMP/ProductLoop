"""Persistent analysis versions and subscriptions. Dashboard reads never invoke Gemini."""
import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from google.cloud import bigquery
from app import config
from app.models.manufacturing import EvidenceRequest, EvidencePackage
from app.rules.dashboard_scope import DASHBOARD_ISSUE_TYPES
from app.services.bigquery import Writer,enabled
from app.services.manufacturing_evidence import generate_evidence,KEYS
from app.services.manufacturing_reasoning import compute,model_input,PROMPT_VERSION

LOG=logging.getLogger(__name__)
_worker_lock=threading.Lock() # Local POC: one worker per backend process.

def encode(value):return json.dumps(value,sort_keys=True,default=str,separators=(',',':'))
def decode(value):return json.loads(value) if isinstance(value,str) else value
def scope_key(request):return 'scope-'+hashlib.sha256(encode(request.model_dump(mode='json')).encode()).hexdigest()[:24]
def material_evidence(package):
    """Deterministic novelty check, not an LLM judgment of root cause.

    Counts, window boundaries, report IDs/status and duplicate observations are
    deliberately excluded. Original snapshots/citations are never rewritten.
    """
    _, records = model_input(package)
    observations = set()
    factory = {}
    batches = set()
    complaint_batches = {r.source_record_key.get('complaint_id'): r.data.get('batch_reference')
                         for r in records if r.source_table == 'complaints'}
    for record in records:
        data = dict(record.data)
        table = record.source_table
        if table == 'complaints':
            batch = data.get('batch_reference')
            if batch: batches.add(batch)
            observations.add(encode({'batch':batch, 'region':data.get('region'),
                'symptoms':sorted(data.get('symptoms') or []),
                'severity':data.get('severity'), 'safety_flag':data.get('safety_flag')}))
        elif table == 'evidence':
            observations.add(encode({'batch':complaint_batches.get(data.get('complaint_id')),
                'symptoms':sorted(data.get('extracted_symptoms') or []),
                'finding':data.get('extracted_summary'), 'status':data.get('extraction_status')}))
        elif table not in ('batches', 'shipments_weekly'):
            # These are already issue-filtered by model_input. Ignore purely
            # administrative timestamps and factory-sample identities/counts.
            for field in ('created_at','updated_at','evidence_refs','source_record_ids',
                          'sample_count','gate_fail_count','gate_fail_note',
                          'units_produced','quantity'):
                data.pop(field, None)
            factory[table+':'+encode(record.source_record_key)] = data
    return {'observations':sorted(observations), 'factory':factory, 'batches':sorted(batches)}

def fingerprint(package):
    return hashlib.sha256(encode(material_evidence(package)).encode()).hexdigest()

def meaningful_change(package, previous):
    if not previous: return True
    if not previous.get('evidence_json'):
        return previous['evidence_fingerprint'] != fingerprint(package)
    old = material_evidence(EvidencePackage.model_validate(decode(previous['evidence_json'])))
    new = material_evidence(package)
    # Expiring reports do not create new cause evidence. New symptom/batch,
    # safety or media findings do. Repeated identical complaints do not.
    if set(new['observations']) - set(old['observations']): return True
    for key, value in new['factory'].items():
        if old['factory'].get(key) != value: return True
    # Missing factory records matter for batches still in scope; dropping a
    # batch solely because the date window rolled is not a source deletion.
    for key, value in old['factory'].items():
        if key not in new['factory'] and value.get('batch_id') in new['batches']: return True
    return False

def related_analysis(w, request):
    # Read-only reuse across windows, never across product/issue/region. Avoid
    # showing evidence from after the selected historical end date.
    rows=query(w,f'''SELECT analysis_id,analysis_version,evidence_fingerprint,analysis_json,evidence_json
      FROM `{w.prefix}.signal_analyses`
      WHERE JSON_VALUE(analysis_json,'$.analysis_request.product_model')=@product
        AND JSON_VALUE(analysis_json,'$.analysis_request.issue_type')=@issue
        AND COALESCE(JSON_VALUE(analysis_json,'$.analysis_request.region'),'')=@region
        AND JSON_VALUE(analysis_json,'$.analysis_request.end_date')<=@end
      ORDER BY generated_at DESC LIMIT 1''',product=request.product_model,
      issue=request.issue_type,region=request.region or '',end=request.end_date.isoformat())
    return rows[0] if rows else None

def query(w,sql,**values):
    params=[bigquery.ScalarQueryParameter(k,'STRING',v if isinstance(v,str) else encode(v)) for k,v in values.items()]
    return [dict(r) for r in w.client.query(sql,job_config=bigquery.QueryJobConfig(query_parameters=params,labels={'app':'productloop','purpose':'analysis-store'})).result(timeout=120)]

def setup():
    w=Writer()
    schemas={
      'signal_analysis_scopes':'scope_key STRING, request_json JSON, status STRING, requested_at TIMESTAMP, checked_at TIMESTAMP, error STRING',
      'signal_analyses':'analysis_id STRING, signal_id STRING, scope_key STRING, analysis_version INT64, evidence_fingerprint STRING, evidence_snapshot_id STRING, model_id STRING, prompt_version STRING, analysis_json JSON, evidence_json JSON, generated_at TIMESTAMP',
      'signal_sme_reviews':'review_id STRING, analysis_id STRING, hypothesis_index INT64, verdict STRING, comment STRING, reviewer_label STRING, reviewed_at TIMESTAMP',
      'signal_analysis_monitor':'monitor_id STRING, source_fingerprint STRING, checked_at TIMESTAMP',
    }
    for table,schema in schemas.items():query(w,f'CREATE TABLE IF NOT EXISTS `{w.prefix}.{table}` ({schema})')

def subscribe(request):
    w=Writer();key=scope_key(request)
    query(w,f'''MERGE `{w.prefix}.signal_analysis_scopes` T USING (SELECT @key scope_key) S ON T.scope_key=S.scope_key
      WHEN MATCHED THEN UPDATE SET status='pending',requested_at=CURRENT_TIMESTAMP(),error=NULL
      WHEN NOT MATCHED THEN INSERT (scope_key,request_json,status,requested_at) VALUES (@key,PARSE_JSON(@request),'pending',CURRENT_TIMESTAMP())''',key=key,request=request.model_dump(mode='json'))
    return {'scope_key':key,'status':'pending'}

def saved(request):
    w=Writer();key=scope_key(request)
    scopes=query(w,f'SELECT status,checked_at,error FROM `{w.prefix}.signal_analysis_scopes` WHERE scope_key=@key LIMIT 1',key=key)
    rows=query(w,f'SELECT analysis_id,analysis_version,evidence_fingerprint,analysis_json FROM `{w.prefix}.signal_analyses` WHERE scope_key=@key ORDER BY analysis_version DESC LIMIT 1',key=key)
    reused = False
    if not rows:
        related = related_analysis(w, request)
        if related:
            rows = [related]
            reused = True
    scope=scopes[0] if scopes else {'status':'unavailable','checked_at':None,'error':None}
    result={'scope_key':key,**scope,'analysis':None,'reviews':[], 'reused_for_scope':reused}
    if reused and not scopes: result['status']='saved_reference'
    if rows:
        row=rows[0];result.update({k:v for k,v in row.items() if k not in ('analysis_json','evidence_json')})
        result['analysis']=decode(row['analysis_json'])
        result['reviews']=query(w,f'SELECT * FROM `{w.prefix}.signal_sme_reviews` WHERE analysis_id=@id ORDER BY reviewed_at DESC',id=row['analysis_id'])
    return result

def version(analysis_id):
    w=Writer();rows=query(w,f'SELECT * FROM `{w.prefix}.signal_analyses` WHERE analysis_id=@id LIMIT 1',id=analysis_id)
    if not rows:return None
    r=rows[0];r['analysis_json']=decode(r['analysis_json']);r['evidence_json']=decode(r['evidence_json']);return r

def review(analysis_id,hypothesis_index,verdict,comment,reviewer_label):
    row=version(analysis_id)
    if row is None:raise LookupError('Analysis not found')
    if not 0<=hypothesis_index<len(row['analysis_json']['interpretation']['hypotheses']):raise ValueError('Invalid hypothesis')
    w=Writer();id='review-'+uuid4().hex
    query(w,f'''INSERT INTO `{w.prefix}.signal_sme_reviews`
      VALUES (@id,@analysis,CAST(@idx AS INT64),@verdict,@comment,@reviewer,CURRENT_TIMESTAMP())''',id=id,analysis=analysis_id,idx=str(hypothesis_index),verdict=verdict,comment=comment,reviewer=reviewer_label)
    return {'review_id':id,'analysis_id':analysis_id}

def evidence_link(analysis_id,ref):
    row=version(analysis_id)
    if not row:return None
    old=next((r for r in row['analysis_json']['evidence'] if r['evidence_ref']==ref),None)
    if not old:return None
    # Explicit evidence verification is read-only and never schedules inference.
    request=EvidenceRequest.model_validate(row['analysis_json']['analysis_request'])
    package=generate_evidence(request);_,current=model_input(package)
    matching=next((r.model_dump(mode='json') for r in current if r.source_table==old['source_table'] and r.source_record_key==old['source_record_key']),None)
    changed=matching is None or encode(matching['data'])!=encode(old['data'])
    raw=[r for r in row['evidence_json']['evidence'] if r['source_table']==old['source_table'] and
        (r['source_record_key']==old['source_record_key'] or (old['evidence_level']=='batch_sample_summary' and r['data'].get('batch_id')==old['data'].get('batch_id')))]
    current_raw=[r.model_dump(mode='json') for r in package.evidence if r.source_table==old['source_table'] and
        (r.source_record_key==old['source_record_key'] or (old['evidence_level']=='batch_sample_summary' and r.data.get('batch_id')==old['data'].get('batch_id')))]
    changed=changed or encode(raw)!=encode(current_raw)
    return {'analysis_id':analysis_id,'analysis_version':row['analysis_version'],'snapshot':old,'snapshot_records':raw,
        'source_changed':changed,'current':matching,'current_records':current_raw,'checked_at':datetime.now(timezone.utc)}

def process_scope(scope):
    w=Writer();key=scope['scope_key'];request=EvidenceRequest.model_validate(decode(scope['request_json']))
    claim=str(scope['requested_at'])
    query(w,f"UPDATE `{w.prefix}.signal_analysis_scopes` SET status='checking',error=NULL WHERE scope_key=@key AND requested_at=CAST(@claim AS TIMESTAMP)",key=key,claim=claim)
    try:
        package=generate_evidence(request);fp=fingerprint(package)
        previous=query(w,f'SELECT analysis_id,evidence_fingerprint,analysis_version,evidence_json FROM `{w.prefix}.signal_analyses` WHERE scope_key=@key ORDER BY analysis_version DESC LIMIT 1',key=key)
        candidate = previous[0] if previous else related_analysis(w,request)
        if meaningful_change(package, candidate):
            result=compute(request,package=package)
            id='analysis-'+uuid4().hex
            ver=(previous[0]['analysis_version'] if previous else 0)+1
            query(w,f'''BEGIN TRANSACTION;
              ASSERT (SELECT IFNULL(MAX(analysis_version),0) FROM `{w.prefix}.signal_analyses` WHERE scope_key=@key)=CAST(@previous AS INT64) AS 'Concurrent analysis version changed';
              INSERT INTO `{w.prefix}.signal_analyses` VALUES (@id,@key,@key,CAST(@version AS INT64),@fp,@snapshot,@model,@prompt,PARSE_JSON(@analysis),PARSE_JSON(@evidence),CURRENT_TIMESTAMP());
              MERGE `{w.prefix}.signals` T USING (SELECT @key signal_id) S ON T.signal_id=S.signal_id
              WHEN MATCHED THEN UPDATE SET computed_at=CURRENT_TIMESTAMP(),payload=PARSE_JSON(@signal)
              WHEN NOT MATCHED THEN INSERT (signal_id,product_model,issue_type,computed_at,payload) VALUES (@key,'X500',@issue,CURRENT_TIMESTAMP(),PARSE_JSON(@signal));
              COMMIT TRANSACTION;''',key=key,id=id,previous=str(ver-1),version=str(ver),fp=fp,snapshot=package.package_id,
              model=result.model,prompt=result.prompt_version,analysis=result.model_dump(mode='json'),evidence=package.model_dump(mode='json'),
              issue=request.issue_type,signal={'scope':request.model_dump(mode='json'),'metrics':package.signal.model_dump(mode='json'),'analysis_id':id})
        query(w,f"UPDATE `{w.prefix}.signal_analysis_scopes` SET status='ready',checked_at=CURRENT_TIMESTAMP(),error=NULL WHERE scope_key=@key AND requested_at=CAST(@claim AS TIMESTAMP)",key=key,claim=claim)
    except Exception:
        LOG.exception('Background scope analysis failed: %s',key)
        query(w,f"UPDATE `{w.prefix}.signal_analysis_scopes` SET status='error',checked_at=CURRENT_TIMESTAMP(),error='Analysis failed validation or source access; worker will retry.' WHERE scope_key=@key AND requested_at=CAST(@claim AS TIMESTAMP)",key=key,claim=claim)

def detect_changes():
    w=Writer()
    from zoneinfo import ZoneInfo
    end=datetime.now(ZoneInfo('Asia/Kolkata')).date()
    regions=[None]+[r['region'] for r in query(w,f"SELECT DISTINCT region FROM `{w.prefix}.complaints` WHERE region IS NOT NULL AND region!=''")]
    requests=[EvidenceRequest(issue_type=issue,region=region,start_date=end-timedelta(days=days-1),end_date=end) for issue in DASHBOARD_ISSUE_TYPES for region in regions for days in (7,30,90)]
    rows=[{'key':scope_key(r),'request':r.model_dump(mode='json')} for r in requests]
    query(w,f'''MERGE `{w.prefix}.signal_analysis_scopes` T USING
      (SELECT JSON_VALUE(x,'$.key') scope_key,JSON_QUERY(x,'$.request') request FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@rows))) x) S ON T.scope_key=S.scope_key
      WHEN NOT MATCHED THEN INSERT (scope_key,request_json,status,requested_at) VALUES (S.scope_key,S.request,'pending',CURRENT_TIMESTAMP())''',rows=rows)
    # Database-side hashes: changes to any source field, inserts or deletes are
    # detected without returning identity or raw text to the polling process.
    hashes=query(w,' UNION ALL '.join(f"SELECT '{t}' source,COUNT(*) n,BIT_XOR(FARM_FINGERPRINT(TO_JSON_STRING(t))) digest FROM `{w.prefix}.{t}` t" for t in [*KEYS,'signal_config']))
    digest=hashlib.sha256(encode({'sources':sorted(hashes,key=lambda r:r['source']),'model':config.MODEL_REASON,'prompt':PROMPT_VERSION}).encode()).hexdigest()
    old=query(w,f"SELECT source_fingerprint FROM `{w.prefix}.signal_analysis_monitor` WHERE monitor_id='sources' LIMIT 1")
    if not old or old[0]['source_fingerprint']!=digest:
        query(w,f'''BEGIN TRANSACTION;
          UPDATE `{w.prefix}.signal_analysis_scopes` SET status='pending',requested_at=CURRENT_TIMESTAMP() WHERE status!='pending';
          MERGE `{w.prefix}.signal_analysis_monitor` T USING (SELECT 'sources' monitor_id) S ON T.monitor_id=S.monitor_id
          WHEN MATCHED THEN UPDATE SET source_fingerprint=@hash,checked_at=CURRENT_TIMESTAMP()
          WHEN NOT MATCHED THEN INSERT VALUES ('sources',@hash,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;''',hash=digest)
    # Retry failed work, but not on every user view.
    query(w,f"UPDATE `{w.prefix}.signal_analysis_scopes` SET status='pending',requested_at=CURRENT_TIMESTAMP() WHERE status='error' AND checked_at<TIMESTAMP_SUB(CURRENT_TIMESTAMP(),INTERVAL 15 MINUTE)")

def start_analysis_worker():
    stop=threading.Event()
    def work():
        if not _worker_lock.acquire(blocking=False):return
        try:
            # Tables are provisioned explicitly, not by browsing the dashboard.
            w=Writer()
            query(w,f"UPDATE `{w.prefix}.signal_analysis_scopes` SET status='pending' WHERE status='checking'")
            checked=0
            while not stop.is_set():
                try:
                    if time.monotonic()-checked>=300:
                        detect_changes();checked=time.monotonic()
                    pending=query(w,f"""SELECT * FROM `{w.prefix}.signal_analysis_scopes` WHERE status='pending'
                      ORDER BY DATE_DIFF(CAST(JSON_VALUE(request_json,'$.end_date') AS DATE),CAST(JSON_VALUE(request_json,'$.start_date') AS DATE),DAY),
                      IF(JSON_VALUE(request_json,'$.region') IS NULL,0,1),requested_at,scope_key LIMIT 1""")
                    if pending:process_scope(pending[0])
                    elif stop.wait(15):break
                except Exception:
                    LOG.exception('Analysis worker check failed')
                    if stop.wait(30):break
        finally:_worker_lock.release()
    thread=None
    if enabled() and os.getenv('PRODUCTLOOP_ANALYSIS_WORKER_ENABLED','1')=='1':
        thread=threading.Thread(target=work,daemon=True,name='manufacturing-analysis');thread.start()
    return stop,thread

if __name__=='__main__':setup();print('Analysis persistence tables ready. No Gemini call performed.')
