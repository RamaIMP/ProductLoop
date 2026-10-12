import json
from pathlib import Path
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api import dashboard
from app.services.seed_dashboard import generate
from app.services.lifecycle import complaint_row
from app.models.taxonomy import ISSUE_TYPES
from app.rules.signals import calculate_signals

CFG=json.loads((Path(__file__).resolve().parents[3]/'bigquery/seed_src/signal_config.json').read_text())

@pytest.mark.parametrize('days', [7,30,90])
def test_dashboard_presets_ignore_fixed_demo_date(monkeypatch, days):
    from types import SimpleNamespace
    from datetime import date, timedelta
    from app.services import signals
    real_calculate = signals.calculate_signals
    def calculate(rows, settings, issues):
        return real_calculate(rows, settings, issues, now=datetime(2026,10,11,20,0,tzinfo=timezone.utc))
    writer = SimpleNamespace(prefix='test',client=SimpleNamespace(query=lambda *a,**k:SimpleNamespace(result=lambda **kw:[])))
    monkeypatch.setattr(signals,'load_source',lambda:(writer,{**CFG,'as_of_date':'2026-10-10'},[]))
    monkeypatch.setattr(signals,'calculate_signals',calculate)
    result=signals.read_overview(days)['signals'][0]
    assert result['window_end']=='2026-10-12'
    assert result['window_start']==(date(2026,10,12)-timedelta(days=days-1)).isoformat()
    custom=signals.read_overview(days,start_date=date(2026,10,1),end_date=date(2026,10,5))['signals'][0]
    assert custom['window_start']=='2026-10-01'
    assert custom['window_end']=='2026-10-05'

def test_manufacturer_scope_excludes_performance_without_changing_taxonomy():
    from app.rules.dashboard_scope import DASHBOARD_ISSUE_TYPES
    rows=[complaint_row(c) for c in generate()['complaints']]
    results=calculate_signals(rows,CFG,DASHBOARD_ISSUE_TYPES)
    all_results=calculate_signals(rows,CFG,ISSUE_TYPES)
    assert 'shaving_performance' in ISSUE_TYPES
    assert all(r['issue_type']!='shaving_performance' for r in results)
    assert len(results)==len(all_results)-1
    assert sum(r['current_count'] for r in results)==sum(r['current_count'] for r in all_results if r['issue_type']!='shaving_performance')
    assert TestClient(app).get('/api/dashboard/complaints?issue_type=shaving_performance&start_date=2026-10-04&end_date=2026-10-10').status_code==422

def test_expected_scenarios_and_daily_totals():
    rows=[complaint_row(c) for c in generate()['complaints']]
    results=calculate_signals(rows,CFG,ISSUE_TYPES)
    indexed={r['issue_type']:r for r in results}
    assert indexed['power_and_charging']['status']=='alert'
    assert indexed['noise_and_vibration']['status']=='watch'
    assert indexed['shaving_performance']['status']=='stable'
    assert indexed['cleaning_and_maintenance']['status']=='declining'
    assert indexed['shaving_head_and_fitment']['status']=='new_issue_activity'
    assert indexed['shaving_head_and_fitment']['growth_pct'] is None
    assert indexed['heat_and_safety']['safety_review']
    for r in results:
        assert sum(d['current'] for d in r['trend'])==r['current_count']
        assert sum(d['baseline'] for d in r['trend'])==r['prior_count']
        assert sum(r['batches'].values())==r['current_count']

def test_exclusions_and_duplicate_suppression():
    row=complaint_row(generate()['complaints'][0])
    rows=[row,row]+[{**row,'complaint_id':str(i),**patch} for i,patch in enumerate([
        {'status':'draft'},{'submitted_at':None},{'consent_share':False},
        {'user_intent':'ask_question'},{'counts_as_complaint':False}])]
    results=calculate_signals(rows,CFG,ISSUE_TYPES)
    assert sum(r['current_count']+r['prior_count'] for r in results)==1

def test_timezone_and_growth_boundary_and_safety_independent():
    row=complaint_row(generate()['complaints'][0])
    rows=[{**row,'complaint_id':str(i),'created_at':'2026-10-03T18:30:00Z','safety_flag':i==0} for i in range(6)]
    rows += [{**row,'complaint_id':'p'+str(i),'created_at':'2026-10-03T18:29:59Z'} for i in range(4)]
    result=calculate_signals(rows,CFG,ISSUE_TYPES)[0]
    result=next(r for r in calculate_signals(rows,CFG,ISSUE_TYPES) if r['issue_type']==row['issue_type'])
    assert result['current_count']==6 and result['prior_count']==4
    assert result['growth_pct']==50 and result['status']=='alert' and result['safety_review']
    with pytest.raises(ValueError): calculate_signals(rows,{**CFG,'baseline_days':30},ISSUE_TYPES)

def test_dashboard_read_and_refresh_api(monkeypatch):
    monkeypatch.setattr(dashboard,'read_signals',lambda:[])
    monkeypatch.setattr(dashboard,'refresh_signals',lambda:[{'status':'watch'}])
    client=TestClient(app)
    assert client.get('/api/dashboard/signals').json()=={'signals':[]}
    assert client.post('/api/dashboard/signals/refresh').json()['signals'][0]['status']=='watch'

@pytest.mark.parametrize('days',[7,30,90])
def test_dashboard_window_selection(monkeypatch,days):
    monkeypatch.setattr(dashboard,'read_overview',lambda n,region=None:{'window_days':n,'region':region})
    client=TestClient(app)
    response=client.get('/api/dashboard/overview',params={'days':days})
    assert response.status_code==200
    assert response.json()['window_days']==days
    assert client.get('/api/dashboard/overview',params={'days':days,'region':'India'}).json()['region']=='India'
    rows=[complaint_row(c) for c in generate()['complaints']]
    for result in calculate_signals(rows,{**CFG,'window_days':days,'baseline_days':days},ISSUE_TYPES):
        assert len(result['trend'])==days
        assert sum(d['current'] for d in result['trend'])==result['current_count']
        assert sum(d['safety'] for d in result['trend'])==result['safety_count']

def test_dashboard_rejects_unknown_window():
    assert TestClient(app).get('/api/dashboard/overview?days=14').status_code==422

def test_custom_dates(monkeypatch):
    monkeypatch.setattr(dashboard,'read_overview',lambda days,region,start,end:{'start':start.isoformat(),'end':end.isoformat()})
    client=TestClient(app)
    assert client.get('/api/dashboard/overview?start_date=2026-10-01&end_date=2026-10-10').json()=={'start':'2026-10-01','end':'2026-10-10'}
    for query in ('start_date=2026-10-01','start_date=bad&end_date=2026-10-10','start_date=2026-10-11&end_date=2026-10-10','start_date=2020-01-01&end_date=2026-10-10'):
        assert client.get('/api/dashboard/overview?'+query).status_code==422

def test_custom_window_calculation():
    rows=[complaint_row(c) for c in generate()['complaints']]
    result=calculate_signals(rows,{**CFG,'as_of_date':'2026-10-09','window_days':3,'baseline_days':3},ISSUE_TYPES)
    for s in result:
        assert s['window_start']=='2026-10-07' and s['window_end']=='2026-10-09'
        assert s['baseline_start']=='2026-10-04' and s['baseline_end']=='2026-10-06'
        assert sum(d['current'] for d in s['trend'])==s['current_count']
