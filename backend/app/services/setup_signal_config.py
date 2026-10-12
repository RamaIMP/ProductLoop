"""Explicitly provision the agreed demo signal settings, not the signal engine."""
import json
import re
from pathlib import Path
from google.cloud import bigquery
from app import config


def setup():
    root = Path(__file__).resolve().parents[3] / 'bigquery'
    settings = json.loads((root / 'seed_src/signal_config.json').read_text())
    assert settings['window_days'] == settings['baseline_days'] > 0
    assert settings['min_events'] >= settings['watch_min_events'] > 0
    assert settings['growth_pct'] >= settings['watch_growth_pct'] >= 0
    assert settings['min_events_safety'] >= 1
    assert settings['batch_rate_alerts_enabled'] is False
    for name in (config.PROJECT_ID,config.BQ_DATASET):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',name):
            raise ValueError('Invalid BigQuery identifier')
    table = f'{config.PROJECT_ID}.{config.BQ_DATASET}.signal_config'
    client = bigquery.Client(project=config.PROJECT_ID)
    statement = re.search(r'CREATE TABLE IF NOT EXISTS signal_config\s*\(.*?;',
        (root / 'tables.sql').read_text(), re.S).group().replace('signal_config',f'`{table}`',1)
    client.query(statement).result(timeout=60)
    schema = {f.name for f in client.get_table(table).schema}
    for name,kind in [('baseline_days','INT64'),('batch_rate_alerts_enabled','BOOL')]:
        if name not in schema:
            client.query(f'ALTER TABLE `{table}` ADD COLUMN IF NOT EXISTS {name} {kind}').result(timeout=60)
    types = {'as_of_date':'DATE','window_days':'INT64','baseline_days':'INT64',
        'min_events':'INT64','min_events_safety':'INT64','watch_min_events':'INT64',
        'min_batch_events':'INT64','batch_rate_alerts_enabled':'BOOL'}
    params = [bigquery.ScalarQueryParameter(k, types.get(k,'FLOAT64'), v) for k,v in settings.items()]
    fields = list(settings)
    # Singleton settings: fail rather than accidentally update multiple configs.
    sql = f'''BEGIN TRANSACTION;
      ASSERT (SELECT COUNT(*) FROM `{table}`) <= 1 AS 'Expected one settings row';
      MERGE `{table}` T USING (SELECT {', '.join('@'+k+' AS '+k for k in fields)}) S ON TRUE
      WHEN MATCHED THEN UPDATE SET {', '.join(k+'=S.'+k for k in fields)}
      WHEN NOT MATCHED THEN INSERT ({', '.join(fields)}) VALUES ({', '.join('S.'+k for k in fields)});
      COMMIT TRANSACTION;'''
    client.query(sql,job_config=bigquery.QueryJobConfig(query_parameters=params)).result(timeout=60)
    rows = [dict(r) for r in client.query(f'SELECT * FROM `{table}`',
        job_config=bigquery.QueryJobConfig(use_query_cache=False)).result(timeout=60)]
    assert len(rows)==1
    rows[0]['as_of_date'] = rows[0]['as_of_date'].isoformat() if rows[0]['as_of_date'] else None
    assert all(rows[0][k] == v for k,v in settings.items())
    print(json.dumps({'table':table,'verified_settings':rows[0]},indent=2))


if __name__ == '__main__':
    setup()
