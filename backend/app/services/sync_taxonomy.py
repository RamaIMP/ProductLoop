"""Explicit reference-table sync: python -m app.services.sync_taxonomy.

Uses the runtime taxonomy, upserts by version + symptom, preserves older versions.
Does not touch complaints or other tables and never invents new symptom labels.
"""
import json
import re
from google.cloud import bigquery
from app import config
from app.models.taxonomy import TAXONOMY


def taxonomy_rows(taxonomy=TAXONOMY):
    rows = []
    for symptom, info in taxonomy['symptoms'].items():
        if info['issue_type'] not in taxonomy['issue_types']:
            raise ValueError(f'Unknown issue type for {symptom}')
        if info['default_severity'] not in ('low', 'medium', 'high'):
            raise ValueError(f'Invalid severity for {symptom}')
        if not all(isinstance(info[k], bool) for k in ('safety', 'counts_as_complaint')):
            raise ValueError(f'Invalid flags for {symptom}')
        rows.append({'symptom':symptom, **{k:info[k] for k in
            ('issue_type','default_severity','safety','counts_as_complaint','description')},
            'taxonomy_version':str(taxonomy['version'])})
    if not rows:
        raise ValueError('Refusing an empty taxonomy')
    return sorted(rows, key=lambda r:r['symptom'])


def sync():
    rows = taxonomy_rows()
    for identifier in (config.PROJECT_ID, config.BQ_DATASET):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', identifier):
            raise ValueError('Invalid BigQuery identifier')
    client = bigquery.Client(project=config.PROJECT_ID)
    table = f'{config.PROJECT_ID}.{config.BQ_DATASET}.taxonomy_symptoms'
    schema = [bigquery.SchemaField(name, kind, mode=mode) for name,kind,mode in (
        ('symptom','STRING','REQUIRED'), ('issue_type','STRING','REQUIRED'),
        ('default_severity','STRING','REQUIRED'), ('safety','BOOLEAN','REQUIRED'),
        ('counts_as_complaint','BOOLEAN','REQUIRED'), ('description','STRING','NULLABLE'),
        ('taxonomy_version','STRING','NULLABLE'))]
    client.create_table(bigquery.Table(table, schema=schema), exists_ok=True)
    fields = list(rows[0])
    source = ', '.join(
        f"CAST(JSON_VALUE(item, '$.{f}') AS BOOL) AS {f}" if f in ('safety','counts_as_complaint')
        else f"JSON_VALUE(item, '$.{f}') AS {f}" for f in fields)
    query = f'''MERGE `{table}` T
        USING (SELECT {source} FROM UNNEST(JSON_QUERY_ARRAY(@rows)) item) S
        ON T.symptom = S.symptom AND T.taxonomy_version = S.taxonomy_version
        WHEN MATCHED THEN UPDATE SET {', '.join(f'{f}=S.{f}' for f in fields)}
        WHEN NOT MATCHED THEN INSERT ({', '.join(fields)}) VALUES ({', '.join('S.'+f for f in fields)})'''
    client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter('rows','STRING',json.dumps(rows))])).result(timeout=60)
    actual = [dict(r) for r in client.query(
        f'SELECT {", ".join(fields)} FROM `{table}` WHERE taxonomy_version=@version ORDER BY symptom',
        job_config=bigquery.QueryJobConfig(use_query_cache=False, query_parameters=[
            bigquery.ScalarQueryParameter('version','STRING',str(TAXONOMY['version']))])).result(timeout=60)]
    if actual != rows:
        raise RuntimeError('Reference-table verification failed; check extra or duplicate rows for this version.')
    print(f'Verified {len(rows)} symptoms across {len(TAXONOMY["issue_types"])} issue types, '
          f'version {TAXONOMY["version"]}, in {table}. Older versions preserved.')


if __name__ == '__main__':
    sync()
