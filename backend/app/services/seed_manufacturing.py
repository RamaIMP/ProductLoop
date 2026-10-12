"""Curated simulated manufacturing evidence, v1. Preview unless --apply.

Only seeded dashboard complaints receive fictional service/return findings.
Application-entered complaints and all consumer tables are never modified.
Factory samples are batch-level, not tests of specific registered serials.
Empty-table-only atomic load prevents accidental replacement or duplicate seeds.
"""
import argparse
import json
import random
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from google.cloud import bigquery
from app.services.bigquery import Writer, expression
from app.services.seed_dashboard import generate as dashboard_seed
from app.services.setup_manufacturing import TABLES

AS_OF=date(2026,10,10)
ROOT=Path(__file__).resolve().parents[3]
COMPONENTS=('motor_assembly','motor_bearing','battery_pack','charging_board','head_latch','head_carrier','housing','seal')
KEYS={'batches':('batch_id',),'shipments_weekly':('batch_id','region','week_start'),
      'production_batches':('batch_id',),'batch_lots':('batch_id','component','lot_id'),
      'change_records':('change_id',),'end_of_line_tests':('unit_test_id',),
      'service_repairs':('repair_id',),'product_returns':('return_id',)}

def day(value):
    if isinstance(value,datetime): return value.astimezone(ZoneInfo('Asia/Kolkata')).date()
    if isinstance(value,date): return value
    return date.fromisoformat(str(value)[:10])

def generate(complaints,units):
    result={name:[] for name in TABLES}
    production=json.loads((ROOT/'data/factory/production_batches.json').read_text())
    rng=random.Random(261010)
    for i,base in enumerate(production):
        batch=base['batch_id'];start=day(base['production_start']);end=day(base['production_end'])
        result['production_batches'].append({**base,'plant':'Plant A','units_produced':5000})
        first=end+timedelta(days=(7-end.weekday())%7 or 7)
        result['batches'].append({'batch_id':batch,'production_month':str(start)[:7],'ship_start':str(first),
            'units_shipped_india':3000,'units_shipped_uk':1500,'units_shipped_total':4500})
        for week in range(4):
            for region,quantity in [('India',750),('UK',375)]:
                result['shipments_weekly'].append({'batch_id':batch,'region':region,'week_start':str(first+timedelta(days=7*week)),'units':quantity})
        for j,component in enumerate(COMPONENTS):
            revision='R1';note=None
            if batch=='B-2026-04-A' and component=='motor_bearing':note='Bearing assembly setting revised before this production run'
            if batch=='B-2026-05-B' and component=='charging_board':revision='C2';note='Connector soldering process adjustment'
            if batch=='B-2026-05-B' and component=='head_latch':revision='T2';note='Latch tooling revision introduced'
            result['batch_lots'].append({'batch_id':batch,'component':component,'lot_id':f'LOT-{start:%y%m}-{j+1:02}-{i+1:02}',
                'supplier':f'SUP-{j+1:02}','received_date':str(start-timedelta(days=7)),
                'quantity':5000,'tooling_revision':revision,'change_note':note})
        for n in range(60):
            acoustic=round(rng.uniform(54,59),1);vibration=round(rng.uniform(.9,1.5),2)
            torque=round(rng.uniform(.97,1.2),2);temp=round(rng.uniform(33,36.5),1);runtime=round(rng.uniform(46,53),1)
            if batch=='B-2026-04-A' and n<18:
                acoustic=round(rng.uniform(59.5,61.9),1);vibration=round(rng.uniform(1.65,1.99),2)
            if batch=='B-2026-05-B' and n<12:torque=round(rng.uniform(.9,.96),2)
            if batch=='B-2026-05-B' and 12<=n<20:temp=round(rng.uniform(36.6,37.9),1)
            # Include failed samples in multiple batches. These are held factory
            # samples, not evidence that failed units were shipped to customers.
            if n==59: runtime=43.5
            if batch=='B-2026-04-A' and n==58:vibration=2.12
            if batch=='B-2026-05-B' and n==58:torque=.86
            passed=acoustic<=62 and vibration<=2 and .9<=torque<=1.3 and temp<=38 and runtime>=45
            result['end_of_line_tests'].append({'unit_test_id':f'EOL-{batch[2:]}-{n+1:03}','batch_id':batch,'test_date':str(end-timedelta(days=n%3)),
                'line':base['lines'][n%len(base['lines'])],'shift':['A','B','C'][n%3],
                'acoustic_db':acoustic,'acoustic_limit_used_db':62,'vibration_rms_mm_s':vibration,
                'lock_torque_nm':torque,'surface_temp_c_5min':temp,'battery_runtime_min':runtime,
                'burn_in_pass':passed,'gate_result':'pass' if passed else 'fail'})
    changes=[('B-2026-04-A','2026-04-01','process_change','Bearing assembly setting changed; compare motor-related findings with other lots.'),
        ('B-2026-05-B','2026-04-30','process_change','Charging connector soldering process adjusted before production.'),
        ('B-2026-05-B','2026-05-01','tooling_change','Head latch tooling revision introduced; inspect engagement tolerance.'),
        ('B-2026-06-C','2026-05-27','supplier_lot_change','Routine motor-bearing lot replenishment; no specification change.'),
        ('B-2026-06-D','2026-06-18','documentation_change','Work instruction illustrations updated; no physical product change.')]
    for i,(batch,when,kind,description) in enumerate(changes):
        result['change_records'].append({'change_id':f'CHG-MFG-{i+1:03}','date':when,'batch_id':batch,'type':kind,'description':description,'approved_by':'Manufacturing engineering'})
    seeded={c['report_id'] for c in dashboard_seed()['complaints']}
    units_by_serial={u['serial_number']:u for u in units}
    counts=Counter()
    preferred={'noise_and_vibration':'B-2026-04-A','power_and_charging':'B-2026-05-B','heat_and_safety':'B-2026-05-B','shaving_head_and_fitment':'B-2026-05-B'}
    ordered=sorted(complaints,key=lambda c:(c['batch_reference']!=preferred.get(c['issue_type'],c['batch_reference']),day(c['created_at']),c['complaint_id']))
    for c in ordered:
        issue=c['issue_type'];serial=c['serial_number'];batch=c['batch_reference']
        if c['complaint_id'] not in seeded or issue=='shaving_performance' or counts[issue]>=3:continue
        repair_date=day(c['created_at'])+timedelta(days=2)
        if repair_date>AS_OF:continue
        u=units_by_serial[serial]
        assert u['batch_id']==batch and u['region']==c['region']
        diagnoses={
            'noise_and_vibration':('Bearing roughness observed on bench inspection','motor_assembly'),
            'power_and_charging':('Intermittent charging-connector contact observed','charging_board'),
            'heat_and_safety':('Local heating observed at charging connection; component cause requires further inspection','charging_board'),
            'shaving_head_and_fitment':('Reduced latch engagement observed during inspection','head_carrier'),
            'cleaning_and_maintenance':('Residue found in head; no manufacturing defect established',None),
            'other_or_unclear':('Reported behaviour not reproduced during inspection',None)}
        diagnosis,part=diagnoses[issue]
        if issue=='power_and_charging' and counts[issue]==2:diagnosis,part='Battery capacity below expected level; connector inspection normal','battery_pack'
        if issue=='noise_and_vibration' and counts[issue]==2:diagnosis,part='Debris found; bearing defect not established',None
        if issue=='cleaning_and_maintenance' and counts[issue]==1:diagnosis,part='Restricted head clearance observed; dimensional confirmation pending','head_carrier'
        if issue=='shaving_head_and_fitment' and counts[issue]==2:diagnosis,part='Head reseated; tooling defect not established',None
        n=len(result['service_repairs'])+1
        result['service_repairs'].append({'repair_id':f'REP-MFG-{n:03}','repair_date':str(repair_date),'batch_id':batch,'region':c['region'],
            'serial_number':serial,'complaint_id':c['complaint_id'],'service_centre':f"Service Centre {'Pune' if c['region']=='India' else 'Manchester'}",
            'diagnosis':diagnosis,'part_replaced':part,'warranty_covered':True,'days_since_purchase':(repair_date-day(u['purchase_date'])).days})
        if counts[issue]==0 and issue not in ('cleaning_and_maintenance','other_or_unclear'):
            result['product_returns'].append({'return_id':f'RET-MFG-{n:03}','return_date':str(repair_date-timedelta(days=1)),
                'batch_id':batch,'region':c['region'],'serial_number':serial,'complaint_id':c['complaint_id'],
                'reason_code':issue,'resolution':'retained_for_inspection' if issue=='heat_and_safety' else 'service_assessment'})
        counts[issue]+=1
    validate(result,complaints,units)
    return result

def validate(data,complaints,units):
    for table,rows in data.items():
        assert len({tuple(r[k] for k in KEYS[table]) for r in rows})==len(rows),table
    batches={r['batch_id']:r for r in data['batches']}
    production={r['batch_id']:r for r in data['production_batches']}
    for table,rows in data.items():
        for r in rows: assert r['batch_id'] in batches,(table,r)
    for batch,b in batches.items():
        shipments=[r for r in data['shipments_weekly'] if r['batch_id']==batch]
        assert sum(r['units'] for r in shipments)==b['units_shipped_total']<=production[batch]['units_produced']
        for region,key in [('India','units_shipped_india'),('UK','units_shipped_uk')]:assert sum(r['units'] for r in shipments if r['region']==region)==b[key]
        assert all(day(r['week_start'])>day(production[batch]['production_end']) for r in shipments)
    for u in units:
        if u['batch_id'] in batches and u.get('purchase_date'):assert day(batches[u['batch_id']]['ship_start'])<=day(u['purchase_date'])
    by_id={c['complaint_id']:c for c in complaints}
    for table,field in [('service_repairs','repair_date'),('product_returns','return_date')]:
        for r in data[table]:
            c=by_id[r['complaint_id']]
            assert (r['serial_number'],r['batch_id'],r['region'])==(c['serial_number'],c['batch_reference'],c['region'])
            assert day(c['created_at'])<day(r[field])<=AS_OF

def run(apply=False):
    w=Writer()
    complaints=[dict(r) for r in w.client.query(f'SELECT complaint_id,serial_number,batch_reference,region,issue_type,created_at FROM `{w.prefix}.complaints`').result(timeout=60)]
    units=[dict(r) for r in w.client.query(f'SELECT serial_number,batch_id,region,purchase_date FROM `{w.prefix}.registered_units`').result(timeout=60)]
    data=generate(complaints,units)
    print(json.dumps({'scenario':'manufacturing-demo-v1','as_of':str(AS_OF),'rows':{k:len(v) for k,v in data.items()},'findings_by_issue':dict(Counter(next(c['issue_type'] for c in complaints if c['complaint_id']==r['complaint_id']) for r in data['service_repairs']))}),flush=True)
    if not apply:return data
    statements=['BEGIN TRANSACTION;'];params=[]
    for table,rows in data.items():
        schema=w.client.get_table(w.prefix+'.'+table).schema
        assert set(rows[0])=={f.name for f in schema},table
        statements.append(f"ASSERT (SELECT COUNT(*) FROM `{w.prefix}.{table}`)=0 AS 'Target must be empty: {table}';")
        columns=', '.join('`'+f.name+'`' for f in schema)
        select=', '.join(expression(f,'$.'+f.name) for f in schema)
        statements.append(f'INSERT INTO `{w.prefix}.{table}` ({columns}) SELECT {select} FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@{table}))) item;')
        params.append(bigquery.ScalarQueryParameter(table,'STRING',json.dumps(rows)))
    statements.append('COMMIT TRANSACTION;')
    w.client.query('\n'.join(statements),job_config=bigquery.QueryJobConfig(query_parameters=params,labels={'app':'productloop','purpose':'simulated-manufacturing'})).result(timeout=180)
    for table,rows in data.items():
        n=list(w.client.query(f'SELECT COUNT(*) n FROM `{w.prefix}.{table}`').result(timeout=60))[0]['n']
        assert n==len(rows),(table,n)
        metadata=w.client.get_table(w.prefix+'.'+table)
        metadata.labels={**(metadata.labels or {}),'data_origin':'simulated','scenario':'manufacturing-demo-v1'}
        w.client.update_table(metadata,['labels'])
        print(f'Verified {table}: {n} rows',flush=True)
    print('Consumer tables unchanged. Manufacturing labels identify simulated provenance.',flush=True)
    return data

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true')
    run(parser.parse_args().apply)
