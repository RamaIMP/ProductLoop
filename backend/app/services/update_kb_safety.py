"""Apply scoped POC safety wording corrections with fresh vectors atomically."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import types
from google.cloud import bigquery

from app.services.load_kb_embeddings import PROJECT, TABLE, MODEL, DIMENSIONS, prepare, validate_vector

TARGETS = {'x500_man_cleaning', 'x500_trb_power_steps',
           'x500_trb_noise_steps', 'x500_trb_noise_escalate',
           'x500_trb_vibration_steps', 'x500_trb_vibration_escalate',
           'x500_trb_battery_steps', 'x500_trb_battery_escalate',
           'x500_trb_fit_steps', 'x500_trb_fit_escalate',
           'x500_trb_heat_steps', 'x500_trb_heat_escalate',
           'x500_trb_power_escalate', 'x500_trb_cutting_steps',
           'x500_trb_cutting_escalate'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    bq = bigquery.Client(project=PROJECT)
    before = [dict(r) for r in bq.query(f'SELECT * FROM `{TABLE}` ORDER BY chunk_id').result(timeout=30)]
    old = {r['chunk_id']: r for r in before}
    expected = {r['chunk_id']: r for r in prepare()}
    if len(before) != 41 or len(old) != 41 or old.keys() != expected.keys():
        raise ValueError('Unexpected table contents; refusing update')
    changed = [key for key in old if old[key]['content_hash'] != expected[key]['content_hash']]
    if set(changed) - TARGETS:
        raise ValueError('Unrelated content changes detected; refusing update')
    print('Changed chunks:', changed, flush=True)
    if not args.apply or not changed:
        return
    backup = Path(__file__).resolve().parents[4] / 'output/kb-safety-backups'
    backup.mkdir(parents=True, exist_ok=True)
    path = backup / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with path.open('x') as handle:
        json.dump(before, handle)
    print('Pre-update backup:', path, flush=True)
    client = genai.Client(vertexai=True, project=PROJECT, location='us-central1',
                          http_options=types.HttpOptions(timeout=60000))
    statements = ['BEGIN TRANSACTION;']
    params = []
    for index, key in enumerate(changed):
        row = expected[key]
        response = client.models.embed_content(model=MODEL, contents=row['title']+'\n'+row['content'],
            config=types.EmbedContentConfig(task_type='RETRIEVAL_DOCUMENT', output_dimensionality=DIMENSIONS))
        row['embedding'] = response.embeddings[0].values
        validate_vector(row['embedding'])
        for name, value in {'id':key,'old':old[key]['content_hash'],'content':row['content'],
                            'hash':row['content_hash'],'model':MODEL}.items():
            params.append(bigquery.ScalarQueryParameter(f'{name}{index}', 'STRING', value))
        params.append(bigquery.ArrayQueryParameter(f'vector{index}', 'FLOAT64', row['embedding']))
        statements += [f'ASSERT (SELECT COUNT(*) FROM `{TABLE}` WHERE chunk_id=@id{index} AND content_hash=@old{index})=1 AS "Concurrent KB change; retry review";',
            f'UPDATE `{TABLE}` SET content=@content{index}, content_hash=@hash{index}, embedding=@vector{index}, embedding_model=@model{index}, review_status="draft" WHERE chunk_id=@id{index};']
    statements.append('COMMIT TRANSACTION;')
    bq.query('\n'.join(statements), job_config=bigquery.QueryJobConfig(query_parameters=params)).result(timeout=60)
    after = {r['chunk_id']:dict(r) for r in bq.query(f'SELECT * FROM `{TABLE}`').result(timeout=30)}
    assert after.keys() == old.keys()
    for key, row in after.items():
        validate_vector(row['embedding'])
        if key in changed:
            assert row['content'] == expected[key]['content']
            assert row['content_hash'] == expected[key]['content_hash']
            assert row['embedding'] == expected[key]['embedding']
            assert row['embedding'] != old[key]['embedding']
        else:
            assert row == old[key], f'Unrelated row changed: {key}'
    print(f'Verified {len(changed)} updated text/vector pairs; {len(old)-len(changed)} rows unchanged.', flush=True)


if __name__ == '__main__':
    main()
