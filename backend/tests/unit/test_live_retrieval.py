from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.taxonomy import Extraction
from app.rules.derive import derive
from app.services import retrieval, gemini
from app.api import consumer


def findings():
    return Extraction(symptoms=['hair_buildup'], confidence=.9, user_intent='ask_question',
        retrieval_query='X500 trapped hair cleaning procedure')


def test_live_query_uses_proposed_query_and_pre_filters(monkeypatch):
    monkeypatch.setenv('PRODUCTLOOP_RAG_MODE','live')
    calls=[]
    def embed(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[.01]*3072)])
    def query(sql, **kwargs):
        assert sql.index('product_model=@product') < sql.index('top_k=>8')
        assert "audience='consumer'" in sql
        assert "review_status='approved'" in sql
        return SimpleNamespace(result=lambda **kw:[{'chunk_id':'clean','title':'Cleaning','text':'Turn off first.','distance':.2}])
    monkeypatch.setattr(retrieval,'embedding_client',lambda:SimpleNamespace(models=SimpleNamespace(embed_content=embed)))
    monkeypatch.setattr(retrieval,'search_client',lambda:SimpleNamespace(query=query))
    result=retrieval.retrieve_for_report('How do I clean it?', findings(), derive(['hair_buildup']))
    assert result['mode']=='rag'
    assert calls[0]['contents']==findings().retrieval_query
    assert calls[0]['config'].task_type=='RETRIEVAL_QUERY'


def test_safety_never_calls_live_retrieval(monkeypatch):
    monkeypatch.setenv('PRODUCTLOOP_RAG_MODE','live')
    monkeypatch.setattr(retrieval,'live_retrieval',lambda *args:pytest.fail('Safety must bypass'))
    assert retrieval.retrieve_for_report('burning',findings(),derive(['burning_smell']))['mode']=='safety_bypass'


def test_cloud_failure_does_not_fall_back_to_mock(monkeypatch):
    monkeypatch.setenv('PRODUCTLOOP_RAG_MODE','live')
    def fail(*args): raise RuntimeError('Cloud unavailable')
    monkeypatch.setattr(retrieval,'live_retrieval',fail)
    with pytest.raises(RuntimeError):
        retrieval.retrieve_for_report('clean',findings(),derive(['hair_buildup']))


@pytest.mark.parametrize('failure',['empty','unavailable','uncited','invalid_citation'])
def test_consumer_failure_is_actionable_without_unsupported_guidance(monkeypatch,failure):
    monkeypatch.setattr(gemini,'understand_conversation',lambda p:gemini.ConversationDecision(extraction=findings(),action='show_guidance'))
    def retrieve(*args):
        if failure=='unavailable': raise RuntimeError('internal details')
        return {'query':'clean','mode':'rag','chunks':[] if failure=='empty' else [{'chunk_id':'clean','title':'Cleaning','text':'Power off.'}]}
    def reason(**kwargs):
        if failure in ('empty','unavailable'): pytest.fail('Must not call answer model')
        if failure=='invalid_citation': raise ValueError('Unknown citation')
        return gemini.GroundedReply(message='Unverified instruction',source_ids=[])
    monkeypatch.setattr(consumer,'retrieve_for_report',retrieve)
    monkeypatch.setattr(gemini,'reason_over_retrieval',reason)
    monkeypatch.setattr(gemini,'reply_to_conversation',lambda p:pytest.fail('No ungrounded fallback'))
    response=TestClient(app).post('/api/conversation',json={'user_id':'rag-test','message':'How do I clean it?'})
    assert response.status_code==200
    body=response.json()
    assert body['action']=='guidance_unavailable'
    assert 'contact support' in body['message']
    assert 'Unverified' not in body['message'] and 'internal details' not in body['message']
    assert body['sources']==[]
