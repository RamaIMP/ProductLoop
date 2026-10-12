"""Scenario-driven dashboard fixtures. Preview by default; --apply loads them.

Provenance/IDs are retained in a separate local manifest, never disguised as
real customer evidence. Existing application records are not modified.
"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from google.cloud import storage
from app import config
from app.models.taxonomy import TAXONOMY
from app.rules.derive import derive
from app.services.lifecycle import get_store, complaint_row, now
from app.services.bigquery import Writer, KEYS, flush_once

SCENARIO = 'productloop-dashboard-2026-10-v1'
PLAN = {
    'power_and_charging': (6,15,['not_charging','battery_drains_fast','slow_charging']),
    'noise_and_vibration': (9,12,['rattling_sound','grinding_sound','increased_vibration']),
    'shaving_performance': (17,17,['missed_hairs','reduced_cutting_quality','pulling_hair','uneven_shave']),
    'cleaning_and_maintenance': (8,5,['hair_buildup','difficult_to_clean']),
    'shaving_head_and_fitment': (0,6,['head_loose','head_not_fitting','head_wobble']),
    'heat_and_safety': (0,2,['burning_smell','excessive_heat']),
    'other_or_unclear': (2,1,['unclear_description']),
}
FILES = {
    'not_charging':('video2_charging_led_off.mp4','video','video/mp4'),
    'grinding_sound':('audio1_rattling_grinding.m4a','audio','audio/mp4'),
    'hair_buildup':('image1_hair_buildup_under_head.jpg','photo','image/jpeg'),
    'head_wobble':('video1_loose_head_wobble.mp4','video','video/mp4'),
    'burning_smell':('audio2_spoken_burnt_smell.m4a','audio','audio/mp4'),
}

def ident(prefix, key):
    return prefix + str(uuid5(NAMESPACE_URL,SCENARIO + '/' + key))

def generate():
    records = {k:[] for k in KEYS}
    units = {}
    index = 0
    for issue,(prior,current,choices) in PLAN.items():
        for period,count in [('baseline',prior),('current',current)]:
            for j in range(count):
                index += 1
                cid = ident('PL-',str(index))
                device = (index-1)%80 + 1
                owner = 'u_' + str(2000 + (device-1)%65 + 1)
                # Most charging reports fall in one batch, without claiming a failure rate.
                batch = 'B-2026-05-B' if issue=='power_and_charging' and j%4 else ['B-2026-04-A','B-2026-05-B','B-2026-06-C'][device%3]
                if device not in units:
                    serial = 'X5-' + batch.replace('B-','').replace('-','') + '-' + f'{1000+device:05}'
                    units[device] = {'unit_id':ident('unit_',str(device)), 'serial_number':serial,
                        'consumer_id':owner,'product_model':'X500','batch_id':batch,
                        'region':['India','India','UK','India','UK'][device%5],
                        'purchase_date':f'2026-08-{1+device%27:02}',
                        'registered_at':f'2026-09-01T{8+device%10:02}:00:00Z',
                        'warranty_status':'Active'}
                unit = units[device]
                # Historical, fully elapsed dates only; avoid future events on the demo day.
                start = datetime(2026,9,27,tzinfo=timezone.utc) if period=='baseline' else datetime(2026,10,4,tzinfo=timezone.utc)
                t = start + timedelta(days=(j*3+index)% (7 if period=='baseline' else 6), hours=6+index%12, minutes=index%55)
                symptom = choices[j%len(choices)]
                outcome = ['helped','not_fixed','not_fixed',None][index%4]
                if issue=='heat_and_safety': outcome='not_fixed'
                cleaning = 'not_applicable' if issue in ('power_and_charging','heat_and_safety','other_or_unclear') else 'no' if outcome=='helped' else 'not_tried' if issue=='shaving_head_and_fitment' else 'yes' if j%2 else 'not_tried'
                extraction = {'product_model':'X500','user_intent':'report_problem','symptoms':[symptom],
                    'context':{'onset':['today','this_week','longer'][index%3],'persists_after_cleaning':cleaning,
                               'during_charging':False if issue!='power_and_charging' else None},
                    'confidence':round(.82+(index%16)/100,2)}
                derived = derive([symptom],extraction['context']).model_dump(mode='json')
                assert derived['issue_type']==issue
                status = 'resolved' if outcome=='helped' else 'awaiting_feedback' if outcome is None else 'unresolved' if index%3==0 and issue!='heat_and_safety' else 'ticket_raised'
                stamp = lambda minutes: (t+timedelta(minutes=minutes)).isoformat()
                report = {'report_id':cid,'user_id':unit['consumer_id'],'unit_id':unit['unit_id'],
                    'serial_number':unit['serial_number'],'batch_reference':unit['batch_id'],'region':unit['region'],
                    'product_model':'X500','created_at':stamp(0),'submitted_at':stamp(4),'updated_at':stamp(12),
                    'extraction':extraction,'derived':derived,'input_types':['text'],'language':'en',
                    'status':status,'outcome':outcome,'resolved_at':stamp(12) if status=='resolved' else None,
                    'ticket_id':'SR-'+uuid5(NAMESPACE_URL,cid).hex[:8].upper() if status=='ticket_raised' else None,
                    'consent_share':True,'taxonomy_version':TAXONOMY['version']}
                records['complaints'].append(report)
                def event(kind,minute,before,after,details=None):
                    records['complaint_events'].append({'event_id':ident('evt_',cid+'/'+kind),
                        'complaint_id':cid,'occurred_at':stamp(minute),'event_type':kind,
                        'previous_status':before,'new_status':after,'actor_type':'system',
                        'new_classification':derived,'details':details or {}})
                event('incident_started',0,None,'draft')
                event('report_submitted',4,'draft','awaiting_feedback')
                if outcome=='helped': event('resolved',12,'awaiting_feedback','resolved')
                elif outcome=='not_fixed':
                    event('not_resolved',9,'awaiting_feedback','unresolved')
                    if status=='ticket_raised': event('ticket_raised',12,'unresolved',status)
                if status=='ticket_raised' and index%4==2:
                    report['service_appointment']={'booking_id':'APT-'+uuid5(NAMESPACE_URL,cid).hex[:10].upper(),
                        'status':'demo_booked','centre_id':'central','centre_name':'XShaver Care — Central',
                        'complaint_id':cid,'product_model':'X500','serial_number':unit['serial_number'],
                        'booked_at':stamp(15),'scheduled_start':'2026-10-12T10:00:00+05:30',
                        'scheduled_end':'2026-10-12T10:30:00+05:30','time_zone':'Asia/Kolkata'}
                    event('service_appointment_booked',15,status,status)
                    report['updated_at']=stamp(15)
    records['registered_units']=list(units.values())
    assert len(records['complaints'])==100
    return records


def validate(records):
    units={u['unit_id']:u for u in records['registered_units']}
    complaints={c['report_id']:c for c in records['complaints']}
    for c in complaints.values():
        u=units[c['unit_id']]
        assert (c['user_id'],c['serial_number'],c['batch_reference'],c['region']) == (u['consumer_id'],u['serial_number'],u['batch_id'],u['region'])
        assert complaint_row(c)['counts_as_complaint']
        assert c['derived']==derive(c['extraction']['symptoms'],c['extraction']['context']).model_dump(mode='json')
        ev=sorted([e for e in records['complaint_events'] if e['complaint_id']==c['report_id']],key=lambda e:e['occurred_at'])
        state=None
        for e in ev:
            assert e['previous_status']==state
            state=e['new_status']
        assert state==c['status']
    for e in records['evidence']:
        assert e['complaint_id'] in complaints and e['gcs_uri'].startswith('gs://')


def signals(rows):
    out={}
    for issue in PLAN:
        selected=[r for r in rows if r.get('counts_as_complaint') and r.get('consent_share') and r.get('submitted_at') and r.get('issue_type')==issue]
        prior=[r for r in selected if '2026-09-27'<=str(r['created_at'])[:10]<='2026-10-03']
        current=[r for r in selected if '2026-10-04'<=str(r['created_at'])[:10]<='2026-10-10']
        p,n=len(prior),len(current)
        growth=round(100*(n-p)/p,2) if p else None
        safety=sum(bool(r.get('safety_flag')) for r in current)
        status='alert' if p and n>=5 and growth>=50 else 'watch' if p and n>=3 and growth>=25 else 'new_issue_activity' if not p and n>=5 else 'low_volume' if n<3 else 'declining' if p and n<p else 'stable'
        out[issue]={'baseline':p,'current':n,'growth_pct':growth,'signal':status,'safety_review':safety>=1}
    return out


def run(apply=False):
    records=generate(); validate(records)
    print(json.dumps({'planned':{k:len(v) for k,v in records.items()},'expected_seed_signals':signals([complaint_row(c) for c in records['complaints']])},indent=2),flush=True)
    if not apply: return
    s=get_store(); w=Writer()
    assert not s.pending(),'Sync existing app writes first'
    # Fail on collisions, not overwrite. Keep provenance and original snapshots separately.
    s.db.execute('CREATE TABLE IF NOT EXISTS demo_seed_manifest (scenario TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    assert not s.db.execute('SELECT 1 FROM demo_seed_manifest WHERE scenario=?',(SCENARIO,)).fetchone(),'Scenario already recorded; do not duplicate'
    original={}
    for kind,key in KEYS.items():
        ids={r['report_id'] if kind=='complaints' else r[key] for r in records[kind]}
        assert not any((r['report_id'] if kind=='complaints' else r[key]) in ids for r in s.all(kind))
        original[kind]=[dict(row) for row in w.client.query(f'SELECT * FROM `{w.prefix}.{kind}`').result(timeout=60)]
        assert not any(r[key] in ids for r in original[kind])
    media=Path(__file__).resolve().parents[3]/'data/test_media'
    bucket=storage.Client(project=config.PROJECT_ID).bucket(config.MEDIA_BUCKET)
    attachments=[]
    for symptom,(filename,kind,mime) in FILES.items():
        candidates=[r for r in records['complaints'] if r['extraction']['symptoms']==[symptom] and r['status']!='resolved'][:2]
        for report in candidates:
            eid=ident('ev_',report['report_id'])
            asset=media/filename
            assert asset.is_file()
            digest=hashlib.sha256(asset.read_bytes()).hexdigest()
            blob=bucket.blob('reference-media/'+eid+asset.suffix)
            if not blob.exists():
                blob.metadata={'scenario':SCENARIO,'sha256':digest,'source':'development-test-fixture'}
                blob.upload_from_filename(str(asset),content_type=mime,if_generation_match=0,timeout=60)
            blob.reload(); assert blob.metadata.get('sha256')==digest
            ts=now()
            evidence={'evidence_id':eid,'complaint_id':report['report_id'],'consumer_id':report['user_id'],
                'kind':kind,'gcs_uri':f'gs://{config.MEDIA_BUCKET}/{blob.name}',
                'original_filename':filename,'content_type':mime,'created_at':ts,'stored_at':ts,
                'storage_status':'uploaded','extraction_status':'not_run','consent_share':True}
            records['evidence'].append(evidence)
            report['input_types'].append('image' if kind=='photo' else kind)
            report['updated_at']=ts
            records['complaint_events'].append({'event_id':ident('evt_',eid),'complaint_id':report['report_id'],
                'evidence_id':eid,'occurred_at':ts,'event_type':'evidence_added','actor_type':'system',
                'previous_status':report['status'],'new_status':report['status'],
                'details':{'storage_status':'uploaded'}})
            attachments.append({'evidence_id':eid,'fixture':str(asset),'sha256':digest,'extraction':'not run; no model findings fabricated'})
    validate(records)
    manifest={'scenario':SCENARIO,'generated_data':True,'created_at':now(),'plan':PLAN,
        'ids':{k:[r['report_id'] if k=='complaints' else r[KEYS[k]] for r in v] for k,v in records.items()},
        'media_provenance':attachments,'original_cloud_records':original,'expected_seed_signals':signals([complaint_row(c) for c in records['complaints']])}
    with s.lock,s.db:
        s.db.execute('INSERT INTO demo_seed_manifest VALUES (?,?)',(SCENARIO,json.dumps(manifest,default=str)))
        for kind,rows in records.items():
            for row in rows:
                key=row['report_id'] if kind=='complaints' else row[KEYS[kind]]
                s.put(kind,key,row)
    while flush_once(w): pass
    cloud={}
    for kind,key in KEYS.items():
        cloud[kind]=[dict(r) for r in w.client.query(f'SELECT * FROM `{w.prefix}.{kind}`').result(timeout=60)]
        indexed={r[key]:r for r in cloud[kind]}
        assert len(indexed)==len(cloud[kind]),'Duplicate keys'
        assert all(indexed[r[key]]==r for r in original[kind]),'Existing records changed'
        assert set(manifest['ids'][kind]) <= set(indexed)
        assert len(cloud[kind])==len(original[kind])+len(records[kind])
    actual=signals(cloud['complaints'])
    assert actual['power_and_charging']['signal']=='alert'
    assert actual['noise_and_vibration']['signal']=='watch'
    assert actual['shaving_performance']['signal']=='stable'
    assert actual['cleaning_and_maintenance']['signal']=='declining'
    assert actual['shaving_head_and_fitment']['signal']=='new_issue_activity'
    assert actual['heat_and_safety']['safety_review']
    assert actual['other_or_unclear']['signal']=='low_volume'
    print(json.dumps({'inserted':{k:len(v) for k,v in records.items()},'cloud_totals':{k:len(v) for k,v in cloud.items()},'combined_signal_checks':actual,'existing_records':'unchanged','pending_writes':s.sync_status()['pending_writes']},indent=2,default=str),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--apply',action='store_true')
    run(parser.parse_args().apply)
