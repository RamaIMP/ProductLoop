"""BigQuery-backed signal snapshots, refreshed explicitly for the local POC."""
import json
from google.cloud import bigquery
from google.api_core.exceptions import NotFound
from app.services.bigquery import Writer
from app.rules.dashboard_scope import DASHBOARD_ISSUE_TYPES as ISSUE_TYPES
from app.rules.signals import calculate_signals


def read_signals():
    w=Writer()
    try:
        rows=w.client.query(f"SELECT payload FROM `{w.prefix}.signals` WHERE product_model='X500' AND signal_id=CONCAT('X500:',issue_type) ORDER BY issue_type").result(timeout=60)
        payloads=[json.loads(r['payload']) if isinstance(r['payload'],str) else r['payload'] for r in rows]
        return [p for p in payloads if p.get('issue_type') in ISSUE_TYPES]
    except NotFound:
        return []


def load_source():
    w=Writer()
    settings=[dict(r) for r in w.client.query(f'SELECT * FROM `{w.prefix}.signal_config`').result(timeout=60)]
    if len(settings)!=1: raise ValueError('Expected one signal configuration')
    # Only fields needed for aggregation; no consumer identity, media URI or raw text.
    rows=[dict(r) for r in w.client.query(f'''SELECT complaint_id, created_at, submitted_at,
      counts_as_complaint, consent_share, user_intent, issue_type, symptoms, safety_flag,
      batch_reference, region, status, severity FROM `{w.prefix}.complaints` WHERE product_model='X500' ''').result(timeout=60)]
    return w, settings[0], rows


def read_overview(days, region=None, start_date=None, end_date=None):
    from datetime import date, datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    if days not in (7,30,90): raise ValueError('Unsupported window')
    if bool(start_date)!=bool(end_date): raise ValueError('Both start and end dates are required')
    if start_date:
        days=(end_date-start_date).days+1
        if not 1<=days<=366: raise ValueError('Choose a range of 1 to 366 days')
    w, settings, rows=load_source()
    # Dashboard presets always roll through today in India time, regardless of
    # the fixed date retained in configuration for reproducible batch jobs.
    settings={**settings,'as_of_date':end_date.isoformat() if end_date else None}
    regions=sorted({r['region'] for r in rows if r.get('region')})
    if region: rows=[r for r in rows if r.get('region')==region]
    result=calculate_signals(rows,{**settings,'window_days':days,'baseline_days':days},ISSUE_TYPES)
    start=date.fromisoformat(result[0]['window_start'])
    end=date.fromisoformat(result[0]['window_end'])
    prior=start-timedelta(days=days)
    eligible={r['complaint_id'] for r in rows if r.get('counts_as_complaint') and r.get('consent_share') and r.get('submitted_at') and r.get('user_intent')=='report_problem' and r.get('status') not in ('draft','abandoned') and r.get('issue_type') in ISSUE_TYPES}
    evidence=w.client.query(f'SELECT evidence_id, complaint_id, created_at, consent_share FROM `{w.prefix}.evidence`').result(timeout=60)
    daily=[0]*days
    current=previous=0
    seen=set()
    issues={r['complaint_id']:r['issue_type'] for r in rows}
    evidence_counts={s['issue_type']:0 for s in result}
    for r in evidence:
        if r['complaint_id'] not in eligible or not r['consent_share'] or not r['created_at'] or r['evidence_id'] in seen: continue
        seen.add(r['evidence_id'])
        dt=r['created_at']
        if not isinstance(dt,datetime): dt=datetime.fromisoformat(str(dt).replace('Z','+00:00'))
        if not dt.tzinfo: dt=dt.replace(tzinfo=timezone.utc)
        day=dt.astimezone(ZoneInfo('Asia/Kolkata')).date()
        if start<=day<=end:
            current+=1
            evidence_counts[issues[r['complaint_id']]]+=1
            daily[(day-start).days]+=1
        elif prior<=day<start: previous+=1
    for signal in result: signal['evidence_count']=evidence_counts[signal['issue_type']]
    return {'signals':result,'evidence':{'current':current,'prior':previous,'trend':daily},'window_days':days,'regions':regions}


def refresh_signals():
    w, settings, rows=load_source()
    result=calculate_signals(rows,settings,ISSUE_TYPES)
    w.client.query(f'''CREATE TABLE IF NOT EXISTS `{w.prefix}.signals` (
      signal_id STRING, product_model STRING, issue_type STRING, computed_at TIMESTAMP, payload JSON)''').result(timeout=60)
    w.client.query(f'''MERGE `{w.prefix}.signals` T USING (
      SELECT CONCAT('X500:',JSON_VALUE(x,'$.issue_type')) signal_id,
      JSON_VALUE(x,'$.issue_type') issue_type, CAST(JSON_VALUE(x,'$.computed_at') AS TIMESTAMP) computed_at,
      x payload FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@rows))) x) S
      ON T.signal_id=S.signal_id
      WHEN MATCHED THEN UPDATE SET payload=S.payload, computed_at=S.computed_at
      WHEN NOT MATCHED THEN INSERT (signal_id,product_model,issue_type,computed_at,payload)
      VALUES (S.signal_id,'X500',S.issue_type,S.computed_at,S.payload)''',job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter('rows','STRING',json.dumps(result))])).result(timeout=60)
    return result


if __name__=='__main__':
    print(json.dumps(refresh_signals(),indent=2))
