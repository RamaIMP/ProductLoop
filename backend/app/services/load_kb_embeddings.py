"""Explicit, non-overwriting POC KB bootstrap. Run with --apply to call cloud APIs."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from google import genai
from google.genai import types
from google.cloud import bigquery

PROJECT = 'project-7eea7443-fac1-4364-9e6'
TABLE = f'{PROJECT}.productloop.kb_chunks'
MODEL = 'gemini-embedding-001'
DIMENSIONS = 3072
SOURCE = Path(__file__).resolve().parents[3] / 'data/x500_rag_knowledge_base_v2.json'
STRING_FIELDS = ('chunk_id', 'product_model', 'source_file', 'section', 'document_type',
                 'title', 'content', 'embedding_model', 'taxonomy_version', 'content_hash',
                 'review_status', 'provenance', 'audience')
ARRAY_FIELDS = ('issue_types', 'symptoms', 'severity_applicability')
SCHEMA = [bigquery.SchemaField(k, 'STRING', mode='REQUIRED' if k == 'chunk_id' else 'NULLABLE')
          for k in STRING_FIELDS] + [bigquery.SchemaField(k, 'STRING', mode='REPEATED') for k in ARRAY_FIELDS] + [
    bigquery.SchemaField('safety_critical', 'BOOL'),
    bigquery.SchemaField('embedding', 'FLOAT64', mode='REPEATED')]


def prepare():
    document = json.loads(SOURCE.read_text())
    rows = []
    for chunk in document['chunks']:
        assert chunk['product_model'] == 'X500'
        assert chunk['title'].strip() and chunk['content'].strip()
        row = dict(chunk, embedding_model=MODEL, taxonomy_version=document['taxonomy_version'],
                   review_status='draft', provenance='fictional_x500_poc',
                   audience='technician' if chunk['chunk_id'] in {
                       'x500_svc_noise', 'x500_svc_battery', 'x500_svc_fit', 'x500_svc_power'} else 'consumer')
        row['content_hash'] = hashlib.sha256((chunk['title'] + '\n' + chunk['content']).encode()).hexdigest()
        rows.append(row)
    assert len(rows) == len({r['chunk_id'] for r in rows}) == 41
    return rows


def validate_vector(values):
    if len(values) != DIMENSIONS or not all(math.isfinite(v) for v in values) or not any(values):
        raise ValueError('Invalid embedding dimensions, nonfinite values, or zero vector')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    rows = prepare()
    print(f'Target: {TABLE}; chunks: {len(rows)}; model: {MODEL}; dimensions: {DIMENSIONS}', flush=True)
    if not args.apply:
        print('Validated source only. No cloud calls. Use --apply to bootstrap an empty table.')
        return
    bq = bigquery.Client(project=PROJECT)
    table = bigquery.Table(TABLE, schema=SCHEMA)
    table.description = 'Fictional X500 POC knowledge base. Draft content requires safety review before consumer deployment.'
    table.labels = {'data_origin': 'simulated', 'review_status': 'draft'}
    bq.create_table(table, exists_ok=True)
    existing = list(bq.query(f'SELECT chunk_id, content_hash, embedding FROM `{TABLE}`').result(timeout=30))
    if existing:
        expected = {r['chunk_id']: r['content_hash'] for r in rows}
        if len(existing) != len(rows) or any(expected.get(r.chunk_id) != r.content_hash for r in existing):
            raise RuntimeError('Existing KB differs; refusing to overwrite. Review a versioned update separately.')
        for row in existing:
            validate_vector(row.embedding)
        print('Matching populated KB already exists; no embedding calls or writes.')
        return
    client = genai.Client(vertexai=True, project=PROJECT, location='us-central1',
                          http_options=types.HttpOptions(timeout=60000))
    for index, row in enumerate(rows, 1):
        response = client.models.embed_content(model=MODEL, contents=row['title'] + '\n' + row['content'],
            config=types.EmbedContentConfig(task_type='RETRIEVAL_DOCUMENT', output_dimensionality=DIMENSIONS))
        values = response.embeddings[0].values
        validate_vector(values)
        row['embedding'] = values
        print(f'Embedded {index}/{len(rows)}: {row["chunk_id"]}', flush=True)
    # Atomic load into an EMPTY destination only. Concurrent population never gets overwritten.
    job = bq.load_table_from_json(rows, TABLE, job_config=bigquery.LoadJobConfig(
        schema=SCHEMA, write_disposition=bigquery.WriteDisposition.WRITE_EMPTY))
    job.result(timeout=120)
    print(f'Loaded {job.output_rows} chunks into {TABLE}', flush=True)


if __name__ == '__main__':
    main()
