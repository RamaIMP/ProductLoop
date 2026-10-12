"""Create the eight manufacturing tables only; never load or replace data."""
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from google.cloud import bigquery
from app.services.bigquery import Writer

TABLES=('batches','shipments_weekly','production_batches','batch_lots',
        'change_records','end_of_line_tests','service_repairs','product_returns')

def setup():
    writer=Writer()
    writer.client.get_dataset(writer.prefix)  # Use the configured existing dataset.
    source=(Path(__file__).resolve().parents[3]/'bigquery/tables.sql').read_text()
    statements={name:re.search(r'CREATE TABLE IF NOT EXISTS '+re.escape(name)+r'\s*\(.*?;',source,re.S).group() for name in TABLES}
    def create(name):
        writer.client.query(statements[name],job_config=bigquery.QueryJobConfig(
            default_dataset=writer.prefix,labels={'app':'productloop','purpose':'manufacturing-setup'})).result(timeout=120)
        table=writer.client.get_table(f'{writer.prefix}.{name}')
        return f'{table.full_table_id}: {len(table.schema)} fields; {table.num_rows} rows'
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(create,TABLES): print(result,flush=True)
    print('Verified eight tables. No records loaded or replaced.',flush=True)

if __name__=='__main__': setup()
