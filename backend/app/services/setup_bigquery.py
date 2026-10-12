"""Explicit opt-in provisioning: python -m app.services.setup_bigquery.

Creates only the four lifecycle tables. Never loads seeds, drops tables or
replaces data. Existing required batch_id needs a separate reviewed relaxation.
"""
import re
from pathlib import Path
from google.cloud import bigquery
from app import config
from app.services.bigquery import KEYS


def setup():
    client = bigquery.Client(project=config.PROJECT_ID)
    dataset_id = f'{config.PROJECT_ID}.{config.BQ_DATASET}'
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = config.LOCATION
    client.create_dataset(dataset, exists_ok=True)
    root = Path(__file__).resolve().parents[3] / 'bigquery'
    source = (root / 'tables.sql').read_text()
    job_config = bigquery.QueryJobConfig(default_dataset=dataset_id)
    for table in KEYS:
        statement = re.search(r'CREATE TABLE IF NOT EXISTS ' + table + r'\s*\(.*?;',source,re.S).group()
        client.query(statement,job_config=job_config).result()
    for name in ('001_incident_lifecycle.sql','002_runtime_lifecycle.sql','003_registration_warranty.sql','004_complaint_summary.sql','005_service_appointment.sql'):
        source = re.sub(r'--[^\n]*','',(root / 'migrations' / name).read_text())
        for statement in source.split(';'):
            match = re.search(r'ALTER TABLE (\w+) ADD COLUMN IF NOT EXISTS (\w+)',statement)
            if not match:
                continue
            table,column = match.groups()
            existing = client.get_table(f'{dataset_id}.{table}')
            if column not in {field.name for field in existing.schema}:
                client.query(statement,job_config=job_config).result()
    print(f'Ready: {dataset_id}; four lifecycle tables. No seed data loaded.')


if __name__ == '__main__':
    setup()
