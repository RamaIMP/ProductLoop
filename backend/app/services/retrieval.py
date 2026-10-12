"""Text-only retrieval. No answer generation and no silent mock fallback."""
import math
import os
from functools import lru_cache
from time import perf_counter

from google import genai
from google.genai import types
from google.cloud import bigquery
from app import config
from app.models.taxonomy import Extraction, Derived
from app.services.mock_guidance import get_guidance


@lru_cache(maxsize=1)
def embedding_client():
    return genai.Client(vertexai=True, project=config.PROJECT_ID, location=config.LOCATION,
                        http_options=types.HttpOptions(timeout=30000))


@lru_cache(maxsize=1)
def search_client():
    return bigquery.Client(project=config.PROJECT_ID)


def live_retrieval(query, extraction):
    started = perf_counter()
    response = embedding_client().models.embed_content(model='gemini-embedding-001', contents=query,
        config=types.EmbedContentConfig(task_type='RETRIEVAL_QUERY', output_dimensionality=3072))
    vector = response.embeddings[0].values
    if len(vector) != 3072 or not all(math.isfinite(v) for v in vector) or not any(vector):
        raise ValueError('Invalid query embedding')
    embed_ms = round((perf_counter()-started)*1000, 1)
    started = perf_counter()
    # Product/audience/review filters run BEFORE top-k. Generic safety guidance
    # remains eligible; an issue-type-only filter can incorrectly exclude it.
    draft_allowed = os.getenv('PRODUCTLOOP_RAG_ALLOW_DRAFT', config.RAG_ALLOW_DRAFT) == '1'
    sql = f'''SELECT base.chunk_id, base.title, base.content AS text,
        base.source_file, base.section, base.review_status, distance
      FROM VECTOR_SEARCH(
        (SELECT * FROM `{config.PROJECT_ID}.{config.BQ_DATASET}.kb_chunks`
         WHERE product_model=@product AND audience='consumer'
           AND embedding_model='gemini-embedding-001' AND ARRAY_LENGTH(embedding)=3072
           AND (review_status='approved' OR (@allow_draft AND review_status='draft'))),
        'embedding', (SELECT @vector AS embedding), top_k=>8, distance_type=>'COSINE')
      WHERE distance <= @max_distance ORDER BY distance LIMIT 5'''
    rows = search_client().query(sql, job_config=bigquery.QueryJobConfig(
        maximum_bytes_billed=100000000,
        query_parameters=[bigquery.ScalarQueryParameter('product','STRING',extraction.product_model),
            bigquery.ScalarQueryParameter('allow_draft','BOOL',draft_allowed),
            bigquery.ScalarQueryParameter('max_distance','FLOAT64',0.65),
            bigquery.ArrayQueryParameter('vector','FLOAT64',vector)])).result(timeout=30)
    chunks = [dict(row) for row in rows]
    search_ms = round((perf_counter()-started)*1000,1)
    return {'query':query, 'chunks':chunks, 'mode':'rag' if chunks else 'no_results',
            'embedding_model':'gemini-embedding-001', 'embedding_dimensions':3072,
            'draft_content_allowed':draft_allowed,
            'timings_ms':{'embedding':embed_ms,'vector_search':search_ms}}


def retrieve_for_report(message: str, extraction: Extraction, derived: Derived) -> dict:
    query = extraction.retrieval_query or ' | '.join([extraction.product_model, message,
                        ', '.join(s.value.replace('_', ' ') for s in extraction.symptoms),
                        extraction.context.model_dump_json()])
    if derived.safety_flag:
        return {'query': query, 'chunks': [], 'mode': 'safety_bypass'}
    mode = os.getenv('PRODUCTLOOP_RAG_MODE', config.RAG_MODE)
    if mode == 'live':
        return live_retrieval(query, extraction)
    if mode != 'mock':
        raise ValueError('RAG mode must be live or mock')
    knowledge = get_guidance(extraction, derived)
    chunks = [{**source, 'text': '\n'.join(knowledge['guidance'])}
              for source in knowledge.get('sources', [])]
    return {'query': query, 'chunks': chunks, 'mode': 'development_mock'}
