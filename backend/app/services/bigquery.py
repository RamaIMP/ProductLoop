"""Background, parameterized BigQuery MERGE writer for the four lifecycle tables."""
import json
import logging
import os
import re
import threading
from google.cloud import bigquery
from app import config
from app.services.lifecycle import get_store, complaint_row

KEYS = {'registered_units':'serial_number', 'complaints':'complaint_id',
        'evidence':'evidence_id', 'complaint_events':'event_id'}
last_error = None
last_synced_at = None

def enabled():
    return os.getenv('PRODUCTLOOP_BIGQUERY_ENABLED', '0') == '1'


def read_profile_units(user_id, client=None):
    """Read authoritative registration fields for Profile; never create records."""
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',config.PROJECT_ID) or not re.fullmatch(r'[a-zA-Z0-9_]+',config.BQ_DATASET):
        raise ValueError('Invalid BigQuery dataset configuration')
    client = client or bigquery.Client(project=config.PROJECT_ID)
    query = f'''
        SELECT unit_id, serial_number, product_model, consumer_id, purchase_date,
               registered_at, batch_id, region, warranty_status
        FROM `{config.PROJECT_ID}.{config.BQ_DATASET}.registered_units`
        WHERE consumer_id = @user_id AND UPPER(TRIM(product_model)) = 'X500'
        ORDER BY registered_at DESC, serial_number
    '''
    rows = client.query(query,job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter('user_id','STRING',user_id)],
        labels={'app':'productloop','purpose':'profile-read'})).result(timeout=20)
    return [dict(row) for row in rows]

def expression(field, path):
    if field.mode == 'REPEATED':
        return f"IFNULL(JSON_VALUE_ARRAY(item, '{path}'), ARRAY<STRING>[])"
    if field.field_type in ('RECORD','STRUCT'):
        children = ', '.join(f"{expression(child, path + '.' + child.name)} AS `{child.name}`" for child in field.fields)
        return f"IF(JSON_QUERY(item, '{path}') IS NULL, NULL, STRUCT({children}))"
    if field.field_type == 'JSON':
        return f"JSON_QUERY(item, '{path}')"
    value = f"JSON_VALUE(item, '{path}')"
    if field.field_type == 'STRING':
        return value
    sql_type = {'BOOLEAN':'BOOL','INTEGER':'INT64','FLOAT':'FLOAT64'}.get(field.field_type,field.field_type)
    return f"CAST({value} AS {sql_type})"

class Writer:
    def __init__(self, client=None):
        self.client = client or bigquery.Client(project=config.PROJECT_ID)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',config.PROJECT_ID) or not re.fullmatch(r'[a-zA-Z0-9_]+',config.BQ_DATASET):
            raise ValueError('Invalid BigQuery dataset configuration')
        self.prefix = f'{config.PROJECT_ID}.{config.BQ_DATASET}'
        self.schemas = {}

    def write(self, batch):
        latest = {}
        for seq,kind,key,payload in batch:
            latest[kind,key] = json.loads(payload)
        statements = ['BEGIN TRANSACTION;']
        parameters = []
        for kind, key in KEYS.items():
            rows = [complaint_row(value) if kind == 'complaints' else value
                    for (table,_),value in latest.items() if table == kind]
            if not rows:
                continue
            table_id = f'{self.prefix}.{kind}'
            if kind not in self.schemas:
                self.schemas[kind] = self.client.get_table(table_id).schema
            fields = self.schemas[kind]
            # Only modify columns managed by the app; preserve other existing columns.
            fields = [f for f in fields if any(f.name in row for row in rows)]
            columns = ', '.join(f'`{f.name}`' for f in fields)
            values = ', '.join(f'S.`{f.name}`' for f in fields)
            selection = ', '.join(f"{expression(f, '$.' + f.name)} AS `{f.name}`" for f in fields)
            update = ', '.join(f'T.`{f.name}`=S.`{f.name}`' for f in fields if f.name != key)
            matched = f'WHEN MATCHED THEN UPDATE SET {update}' if kind != 'complaint_events' else ''
            statements.append(f"""
                MERGE `{table_id}` T
                USING (SELECT {selection} FROM UNNEST(JSON_QUERY_ARRAY(PARSE_JSON(@{kind}))) item) S
                ON T.`{key}`=S.`{key}`
                {matched}
                WHEN NOT MATCHED THEN INSERT ({columns}) VALUES ({values});
            """)
            parameters.append(bigquery.ScalarQueryParameter(kind,'STRING',json.dumps(rows)))
        statements.append('COMMIT TRANSACTION;')
        self.client.query('\n'.join(statements),job_config=bigquery.QueryJobConfig(
            query_parameters=parameters, labels={'app':'productloop','purpose':'lifecycle'})).result()

def flush_once(writer=None):
    global last_error,last_synced_at
    batch = get_store().pending()
    if not batch:
        return False
    (writer or Writer()).write(batch)
    get_store().ack(batch[-1][0])
    from app.services.lifecycle import now
    last_error = None
    last_synced_at = now()
    return True

def sync_status():
    return {**get_store().sync_status(), 'bigquery_enabled':enabled(),
            'last_synced_at':last_synced_at, 'last_error':last_error}

def start_worker():
    stop = threading.Event()
    def work():
        global last_error
        writer = None
        while not stop.wait(5 if last_error is None else 30):
            try:
                writer = writer or Writer()
                flush_once(writer)
            except Exception as exc:
                last_error = type(exc).__name__
                logging.getLogger(__name__).warning('BigQuery sync failed (%s); records remain queued',last_error)
    thread = None
    if enabled():
        thread = threading.Thread(target=work,daemon=True,name='productloop-bigquery')
        thread.start()
    return stop,thread
