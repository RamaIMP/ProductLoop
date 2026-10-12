"""Read-only BigQuery snapshot for the four requested reference CSVs."""
import json
from pathlib import Path
from google.cloud import bigquery
from app import config

client = bigquery.Client(project=config.PROJECT_ID)
snapshot = list(client.query('SELECT CURRENT_TIMESTAMP() AS t').result())[0]['t']
tables = {}
for name, key in [('complaints','complaint_id'),('evidence','evidence_id'),
                  ('complaint_events','event_id'),('registered_units','serial_number')]:
    table_id = f'{config.PROJECT_ID}.{config.BQ_DATASET}.{name}'
    schema = client.get_table(table_id).schema
    query = f'SELECT TO_JSON_STRING(t) AS record FROM `{table_id}` AS t FOR SYSTEM_TIME AS OF @snapshot ORDER BY `{key}`'
    result = client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter('snapshot','TIMESTAMP',snapshot)])).result(timeout=60)
    rows = [json.loads(r['record']) for r in result]
    assert len({r[key] for r in rows}) == len(rows), f'Duplicate keys in {name}'
    tables[name] = {'headers':[f.name for f in schema], 'rows':rows}
    print(f'{name}: {len(rows)} rows')
out = Path(__file__).resolve().parents[2] / 'output/table-reference-build/snapshot.json'
out.write_text(json.dumps({'snapshot_utc':snapshot.isoformat(), 'dataset':f'{config.PROJECT_ID}.{config.BQ_DATASET}', 'tables':tables},ensure_ascii=False), encoding='utf-8')
print(f'Snapshot: {snapshot.isoformat()}')
