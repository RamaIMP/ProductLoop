from fastapi.testclient import TestClient
from app.main import app
from app.api import dashboard

def test_list_validates_and_passes_scope(monkeypatch):
    monkeypatch.setattr(dashboard,'list_complaints',lambda issue,start,end,region,page,size:{'issue':issue,'region':region,'page':page})
    c=TestClient(app)
    url='/api/dashboard/complaints?issue_type=power_and_charging&start_date=2026-10-04&end_date=2026-10-10&region=India&page=2'
    assert c.get(url).json()=={'issue':'power_and_charging','region':'India','page':2}
    assert c.get(url+'&page_size=100').status_code==422
    assert c.get(url.replace('power_and_charging','invalid')).status_code==422
    assert c.get(url.replace('2026-10-04','2026-10-11')).status_code==422

def test_detail_and_media_not_found(monkeypatch):
    monkeypatch.setattr(dashboard,'complaint_detail',lambda id:None)
    monkeypatch.setattr(dashboard,'evidence_media',lambda id,eid:None)
    c=TestClient(app)
    assert c.get('/api/dashboard/complaints/missing').status_code==404
    assert c.get('/api/dashboard/complaints/missing/evidence/missing/media').status_code==404

def test_media_headers(monkeypatch):
    monkeypatch.setattr(dashboard,'evidence_media',lambda id,eid:(b'image','image/jpeg'))
    r=TestClient(app).get('/api/dashboard/complaints/c/evidence/e/media')
    assert r.status_code==200 and r.content==b'image'
    assert r.headers['cache-control']=='private, no-store'
    assert r.headers['x-content-type-options']=='nosniff'

def test_external_review_denied():
    c=TestClient(app,client=('192.0.2.1',1000))
    assert c.get('/api/dashboard/complaints/c').status_code==403
