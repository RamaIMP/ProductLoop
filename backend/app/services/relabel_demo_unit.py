"""Explicit, scoped demo-registration correction. Run with the backend stopped.

Keeps unit/consumer/complaint IDs stable. Archives original local records for
recovery, updates the cloud serial key, then uses the regular outbox for sync.
Safe to rerun after an interrupted sync. Not an API or automatic startup action.
"""
import json
from google.cloud import bigquery
from app.services.lifecycle import get_store, now
from app.services.bigquery import Writer, flush_once

OLD = 'DEMO-X500-RAMA-001'
NEW = 'X5-202604A-00088'
BATCH = 'B-2026-04-A'
UNIT = 'unit_e183f72f8bea4edcaab21a24b63b08e8'
OWNER = 'demo-ramachandra'


def run():
    store = get_store()
    writer = Writer()
    assert not store.pending(), 'Drain the existing outbox before this correction.'
    source = store.get('registered_units', OLD) or store.get('registered_units', NEW)
    assert source and source['unit_id'] == UNIT and source['consumer_id'] == OWNER
    destination = store.get('registered_units', NEW)
    assert not destination or destination['unit_id'] == UNIT, 'Local serial conflict'
    reports = [r for r in store.all('complaints')
               if r.get('unit_id') == UNIT or r.get('serial_number') == OLD]
    assert all(r['user_id'] == OWNER and r.get('serial_number') in (OLD, NEW, None) for r in reports)
    params = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter(k,'STRING',v) for k,v in
        [('old',OLD),('new',NEW),('unit',UNIT),('owner',OWNER),('batch',BATCH)]])
    table = writer.prefix + '.registered_units'
    cloud = [dict(r) for r in writer.client.query(
        f'SELECT * FROM `{table}` WHERE serial_number IN (@old,@new) OR unit_id=@unit',
        job_config=params).result(timeout=60)]
    assert len(cloud) == 1 and cloud[0]['unit_id'] == UNIT and cloud[0]['consumer_id'] == OWNER, 'Cloud registration conflict'
    cloud_reports = [dict(r) for r in writer.client.query(
        f'SELECT complaint_id,consumer_id FROM `{writer.prefix}.complaints` WHERE unit_id=@unit OR serial_number IN (@old,@new)',
        job_config=params).result(timeout=60)]
    assert all(r['consumer_id'] == OWNER and r['complaint_id'] in {x['report_id'] for x in reports}
               for r in cloud_reports), 'Cloud-only or conflicting complaints require review'
    with store.lock, store.db:
        store.db.execute('CREATE TABLE IF NOT EXISTS registration_correction_backup (migration TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        store.db.execute('INSERT OR IGNORE INTO registration_correction_backup VALUES (?,?)',
            ('x500-realistic-identifiers', json.dumps({'captured_at':now(),'registration':source,
                'complaints':reports,'cloud_registration':cloud}, default=str)))
    # Update the existing key, rather than inserting a second registration.
    writer.client.query(f'''UPDATE `{table}` SET serial_number=@new, batch_id=@batch
        WHERE unit_id=@unit AND consumer_id=@owner AND serial_number IN (@old,@new)''',
        job_config=params).result(timeout=60)
    with store.lock, store.db:
        updated = {**source,'serial_number':NEW,'batch_id':BATCH}
        store.put('registered_units', NEW, updated)
        store.db.execute('DELETE FROM records WHERE kind=? AND id=?', ('registered_units',OLD))
        for before in reports:
            after = {**before,'unit_id':UNIT,'serial_number':NEW,'batch_reference':BATCH,
                     'region':source.get('region'),'product_model':source['product_model']}
            if before.get('service_appointment'):
                after['service_appointment'] = {**before['service_appointment'],'serial_number':NEW}
            if after != before:
                after['updated_at'] = now()
                store.put('complaints', before['report_id'], after)
                store.event(before['report_id'], 'device_registration_corrected', before, after,
                    details={'old_serial_number':OLD,'serial_number':NEW,'batch_reference':BATCH})
    while flush_once(writer):
        pass
    verified = [dict(r) for r in writer.client.query(
        f'SELECT complaint_id,serial_number,batch_reference,unit_id FROM `{writer.prefix}.complaints` WHERE unit_id=@unit',
        job_config=params).result(timeout=60)]
    assert {r['complaint_id'] for r in verified} == {r['report_id'] for r in reports}
    assert all(r['serial_number']==NEW and r['batch_reference']==BATCH for r in verified)
    registrations = list(writer.client.query(
        f'SELECT serial_number,batch_id FROM `{table}` WHERE unit_id=@unit OR serial_number=@old',
        job_config=params).result(timeout=60))
    assert len(registrations)==1 and registrations[0]['serial_number']==NEW and registrations[0]['batch_id']==BATCH
    print(json.dumps({'serial_number':NEW,'batch_id':BATCH,'linked_complaints_updated':len(verified),
        'pending_writes':store.sync_status()['pending_writes'],'verified':'local and BigQuery'}))


if __name__ == '__main__':
    run()
