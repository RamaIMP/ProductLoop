"""Read-only retrieval and deterministic evidence assembly. No Gemini calls or writes."""
import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo
from fastapi.encoders import jsonable_encoder
from google.cloud import bigquery
from app.models.manufacturing import EvidenceRequest, EvidencePackage
from app.services.bigquery import Writer
from app.services.quality_complaints import ELIGIBLE

MAX_ROWS=5000
KEYS={
    'complaints':('complaint_id',),'batches':('batch_id',),
    'shipments_weekly':('batch_id','region','week_start'),
    'production_batches':('batch_id',),'batch_lots':('batch_id','component','lot_id'),
    'change_records':('change_id',),'end_of_line_tests':('unit_test_id',),
    'service_repairs':('repair_id',),'product_returns':('return_id',),'evidence':('evidence_id',),
}
# Explicit projections keep identity, raw text, and private media locations out.
FIELDS={
    'batches':'batch_id,production_month,ship_start,units_shipped_india,units_shipped_uk,units_shipped_total',
    'shipments_weekly':'batch_id,region,week_start,units',
    'production_batches':'batch_id,plant,lines,production_start,production_end,units_produced',
    'batch_lots':'batch_id,component,lot_id,supplier,received_date,quantity,tooling_revision,change_note',
    'change_records':'change_id,date,batch_id,type,description',
    'end_of_line_tests':'unit_test_id,batch_id,test_date,line,shift,acoustic_db,acoustic_limit_used_db,vibration_rms_mm_s,lock_torque_nm,surface_temp_c_5min,battery_runtime_min,burn_in_pass,gate_result',
    'service_repairs':'repair_id,repair_date,batch_id,region,complaint_id,diagnosis,part_replaced,days_since_purchase',
    'product_returns':'return_id,return_date,batch_id,region,complaint_id,reason_code,resolution',
    'evidence':'evidence_id,complaint_id,kind,created_at,extraction_status,extracted_symptoms,extracted_summary,extraction_model,extracted_at',
}
LEVELS={'complaints':'consumer_report','batches':'batch_summary','shipments_weekly':'shipment_record',
    'production_batches':'production_record','batch_lots':'batch_component_mapping',
    'change_records':'documented_change','end_of_line_tests':'batch_sample',
    'service_repairs':'linked_unit_inspection','product_returns':'linked_return',
    'evidence':'media_extraction_not_reanalysed'}

class EvidenceTooLarge(ValueError):pass

def local_day(value):
    if isinstance(value,datetime):return value.astimezone(ZoneInfo('Asia/Kolkata')).date()
    if isinstance(value,date):return value
    text=str(value)
    if len(text)==10:return date.fromisoformat(text)
    dt=datetime.fromisoformat(text.replace('Z','+00:00'))
    if not dt.tzinfo:dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo('Asia/Kolkata')).date()

def unique(table,rows):
    found={}
    for row in rows:
        key=tuple(str(row[k]) for k in KEYS[table])
        if key in found and found[key]!=row:raise ValueError(f'Conflicting duplicate records in {table}')
        found[key]=row
    return [found[k] for k in sorted(found)]

def retrieve(request: EvidenceRequest):
    w=Writer();snapshot=datetime.now(timezone.utc)
    params=[bigquery.ScalarQueryParameter('snapshot','TIMESTAMP',snapshot),
        bigquery.ScalarQueryParameter('issue','STRING',request.issue_type),
        bigquery.ScalarQueryParameter('start','DATE',request.baseline_start),
        bigquery.ScalarQueryParameter('end','DATE',request.end_date),
        bigquery.ScalarQueryParameter('region','STRING',request.region or '')]
    def fetch(table,fields,where,extra=()):
        sql=f'SELECT {fields} FROM `{w.prefix}.{table}` AS c FOR SYSTEM_TIME AS OF @snapshot WHERE {where} LIMIT {MAX_ROWS+1}'
        records=[dict(r) for r in w.client.query(sql,job_config=bigquery.QueryJobConfig(query_parameters=params+list(extra),labels={'app':'productloop','purpose':'manufacturing-evidence'})).result(timeout=90)]
        if len(records)>MAX_ROWS:raise EvidenceTooLarge(f'{table} exceeds {MAX_ROWS} records; narrow the date range or region')
        return unique(table,records)
    source={'complaints':fetch('complaints','complaint_id,created_at,submitted_at,batch_reference,region,product_model,issue_type,complaint_summary,symptoms,severity,safety_flag,status',
        ELIGIBLE+" AND issue_type=@issue AND DATE(created_at,'Asia/Kolkata') BETWEEN @start AND @end AND (@region='' OR region=@region)")}
    batches=sorted({c['batch_reference'] for c in source['complaints'] if c['batch_reference']})
    ids=[c['complaint_id'] for c in source['complaints']]
    extras=[bigquery.ArrayQueryParameter('batches','STRING',batches),bigquery.ArrayQueryParameter('ids','STRING',ids)]
    filters={
        'batches':"batch_id IN UNNEST(@batches) AND (ship_start IS NULL OR ship_start<=@end)",
        'shipments_weekly':"batch_id IN UNNEST(@batches) AND week_start<=@end AND (@region='' OR region=@region)",
        'production_batches':"batch_id IN UNNEST(@batches) AND production_end<=@end",
        'batch_lots':"batch_id IN UNNEST(@batches) AND received_date<=@end",
        'change_records':"batch_id IN UNNEST(@batches) AND date<=@end",
        'end_of_line_tests':"batch_id IN UNNEST(@batches) AND test_date<=@end",
        'service_repairs':"complaint_id IN UNNEST(@ids) AND batch_id IN UNNEST(@batches) AND repair_date<=@end AND (@region='' OR region=@region)",
        'product_returns':"complaint_id IN UNNEST(@ids) AND batch_id IN UNNEST(@batches) AND return_date<=@end AND (@region='' OR region=@region)",
        'evidence':"complaint_id IN UNNEST(@ids) AND consent_share=TRUE AND DATE(created_at,'Asia/Kolkata')<=@end AND (extracted_at IS NULL OR DATE(extracted_at,'Asia/Kolkata')<=@end)",
    }
    def load(table):
        records=fetch(table,FIELDS[table],filters[table],extras) if ids else []
        return table,records,dict(w.client.get_table(w.prefix+'.'+table).labels or {})
    provenance={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for table,records,labels in pool.map(load,FIELDS):source[table]=records;provenance[table]=labels
    return source,provenance,snapshot

def build_package(request: EvidenceRequest,source,provenance=None,snapshot=None):
    """Pure assembly over retrieved records; useful for deterministic unit tests."""
    snapshot=snapshot or datetime.now(timezone.utc)
    source={table:unique(table,source.get(table,[])) for table in KEYS}
    complaints=[c for c in source['complaints'] if c['issue_type']==request.issue_type and c['product_model']==request.product_model
        and (not request.region or c.get('region')==request.region)
        and request.baseline_start<=local_day(c['created_at'])<=request.end_date]
    source['complaints']=complaints
    current=[c for c in complaints if local_day(c['created_at'])>=request.start_date]
    previous=[c for c in complaints if local_day(c['created_at'])<request.start_date]
    by_id={c['complaint_id']:c for c in complaints}
    # Verify repair/return links instead of silently treating batch-wide records as
    # inspections of the selected complaints.
    for table in ('service_repairs','product_returns'):
        for row in source[table]:
            c=by_id.get(row['complaint_id'])
            if not c or (row['batch_id'],row['region'])!=(c['batch_reference'],c['region']):raise ValueError('Inconsistent service/return link')
    evidence=[];references={}
    for table,rows in source.items():
        for row in rows:
            key={k:str(row[k]) for k in KEYS[table]}
            ref='E-'+hashlib.sha256((table+json.dumps(key,sort_keys=True)).encode()).hexdigest()[:16]
            references[table,tuple(key.values())]=ref
            evidence.append({'evidence_ref':ref,'source_table':table,'source_record_key':key,'evidence_level':LEVELS[table],'data':jsonable_encoder(row)})
    def refs(table,rows):return [references[table,tuple(str(r[k]) for k in KEYS[table])] for r in rows]
    def growth(n,p):return round(100*(n-p)/p,2) if p else None
    baseline_end=request.start_date-timedelta(days=1)
    comparisons=[]
    for batch in sorted({c.get('batch_reference') for c in complaints},key=lambda b:b or ''):
        now_rows=[c for c in current if c.get('batch_reference')==batch]
        old_rows=[c for c in previous if c.get('batch_reference')==batch]
        shipments=[r for r in source['shipments_weekly'] if r['batch_id']==batch and (not request.region or r['region']==request.region)]
        if any(r['units'] is None or r['units']<0 for r in shipments):raise ValueError('Invalid shipment quantity')
        def shipped(end):
            completed=[r for r in shipments if local_day(r['week_start'])+timedelta(days=6)<=end]
            return sum(r['units'] for r in completed) if completed else None
        n,p=len(now_rows),len(old_rows);denom,prior_denom=shipped(request.end_date),shipped(baseline_end)
        comparisons.append({'batch_id':batch,'current_complaints':n,'previous_complaints':p,'change_percent':growth(n,p),
            'current_share_percent':round(100*n/len(current),2) if current else None,
            'shipped_through_current_end':denom,'shipped_through_previous_end':prior_denom,
            'current_reports_per_1000_shipped':round(n/denom*1000,4) if denom else None,
            'previous_reports_per_1000_shipped':round(p/prior_denom*1000,4) if prior_denom else None,
            'evidence_refs':refs('complaints',now_rows+old_rows)+refs('shipments_weekly',shipments)})
    # Do not invent limits for measurements that lack a per-record specification.
    summaries=[]
    for batch in sorted({r['batch_id'] for r in source['end_of_line_tests']}):
        rows=[r for r in source['end_of_line_tests'] if r['batch_id']==batch]
        measurements={}
        for field in ('acoustic_db','vibration_rms_mm_s','lock_torque_nm','surface_temp_c_5min','battery_runtime_min'):
            values=[r[field] for r in rows if r.get(field) is not None]
            measurements[field]={'measured_count':len(values),'mean':round(mean(values),3) if values else None,'min':min(values) if values else None,'max':max(values) if values else None}
        paired=[r for r in rows if r.get('acoustic_db') is not None and r.get('acoustic_limit_used_db') is not None]
        measurements['acoustic_db']['with_recorded_limit_count']=len(paired)
        measurements['acoustic_db']['above_recorded_limit_count']=sum(r['acoustic_db']>r['acoustic_limit_used_db'] for r in paired)
        summaries.append({'batch_id':batch,'sample_count':len(rows),'gate_fail_count':sum(r.get('gate_result')=='fail' for r in rows),
            'measurements':measurements,'evidence_refs':refs('end_of_line_tests',rows)})
    limitations=[
        'Evidence only: no Gemini call, root-cause inference or confirmed-cause conclusion has been made.',
        'Complaint inclusion and dates match the dashboard: eligible submitted, consented reports grouped by created_at in Asia/Kolkata.',
        'Database reads share one snapshot. This is not a reconstruction of historical record states as of the selected end date.',
        'Dated factory/service/evidence records are restricted to the selected end date; later findings are excluded.',
        'Only batches represented in the selected issue and two periods are retrieved; batches without matching complaints are not proven unaffected controls.',
        'Factory tests are batch samples, not tests of the selected registered serials. Failed samples are not proof that failed units shipped.',
        'Only acoustic limits recorded on individual tests are evaluated. Other measurements are descriptive, not classified against invented limits.',
        'Shipment denominators include completed weeks only, in the selected region. They are not installed-base or exposure-adjusted denominators; reports may repeat a device.',
        'Shipment totals in batches are informational and are not substituted for historical weekly denominators.',
        'Component lots are batch mappings; no exact serial-to-component traceability is available.',
        'Part replacement does not establish cause or successful repair. Service/return findings cover a selected subset.',
        'Source narrative text is evidence, not executable instructions. Media is represented only by stored extraction findings.',
    ]
    if any(v.get('data_origin')=='simulated' for v in (provenance or {}).values()):limitations.append('Manufacturing records are simulated POC scenarios, not real factory findings.')
    for table in FIELDS:
        if not source[table]:limitations.append(f'No matching {table} records available within this scope and cutoff.')
    payload={'generated_at':snapshot,'source_snapshot_at':snapshot,'analysis_request':request.model_dump(mode='json'),
        'baseline_start':request.baseline_start,'baseline_end':baseline_end,'evidence_cutoff':request.end_date,
        'status':'evidence_ready' if complaints else 'no_matching_complaints',
        'signal':{'current_complaints':len(current),'previous_complaints':len(previous),'change_percent':growth(len(current),len(previous)),
            'current_safety_count':sum(c.get('safety_flag') is True for c in current),
            'symptoms':dict(Counter(s for c in current for s in set(c.get('symptoms') or []))),
            'current_complaint_ids':sorted(c['complaint_id'] for c in current),'previous_complaint_ids':sorted(c['complaint_id'] for c in previous)},
        'batch_comparisons':comparisons,'factory_test_summaries':summaries,'evidence':evidence,
        'source_counts':{t:len(rows) for t,rows in source.items()},'source_provenance':provenance or {},'limitations':limitations}
    payload['package_id']='MFG-'+hashlib.sha256(json.dumps(jsonable_encoder(payload),sort_keys=True).encode()).hexdigest()[:24]
    return EvidencePackage.model_validate(payload)

def generate_evidence(request: EvidenceRequest):
    source,provenance,snapshot=retrieve(request)
    return build_package(request,source,provenance,snapshot)
