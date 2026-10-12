from app.services.seed_dashboard import generate, validate, signals, PLAN
from app.services.lifecycle import complaint_row

def test_scenario_links_classification_and_history_are_consistent():
    rows=generate()
    validate(rows)
    assert len(rows['complaints'])==100
    assert len(rows['registered_units'])==80
    assert len({r['consumer_id'] for r in rows['registered_units']})==65
    assert all(c['user_id']!='demo-ramachandra' for c in rows['complaints'])
    assert rows==generate()

def test_scenarios_exercise_expected_trends_without_random_classification():
    results=signals([complaint_row(c) for c in generate()['complaints']])
    for issue,(prior,current,_) in PLAN.items():
        assert results[issue]['baseline']==prior
        assert results[issue]['current']==current
    assert results['power_and_charging']['signal']=='alert'
    assert results['noise_and_vibration']['signal']=='watch'
    assert results['shaving_performance']['signal']=='stable'
    assert results['cleaning_and_maintenance']['signal']=='declining'
    assert results['shaving_head_and_fitment']['signal']=='new_issue_activity'
    assert results['heat_and_safety']['safety_review']
    assert results['other_or_unclear']['signal']=='low_volume'
