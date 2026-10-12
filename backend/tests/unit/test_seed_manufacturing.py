from copy import deepcopy
from collections import Counter
from app.services.seed_dashboard import generate as dashboard_seed
from app.services.seed_manufacturing import generate,validate
from app.services.lifecycle import complaint_row
import pytest

def test_linked_manufacturing_seed_is_deterministic_and_preserves_sources():
    source=dashboard_seed()
    complaints=[complaint_row(c) for c in source['complaints']]
    units=source['registered_units']
    original=deepcopy(complaints)
    data=generate(complaints,units)
    assert data==generate(complaints,units)
    assert complaints==original
    assert len(data['batches'])==7
    assert len(data['batch_lots'])==56
    assert len(data['end_of_line_tests'])==420
    assert set(r['gate_result'] for r in data['end_of_line_tests'])=={'pass','fail'}
    lookup={r['complaint_id']:r['issue_type'] for r in complaints}
    assert len({lookup[r['complaint_id']] for r in data['service_repairs']})==6
    assert all(lookup[r['complaint_id']]!='shaving_performance' for r in data['service_repairs'])
    broken=deepcopy(data);broken['shipments_weekly'][0]['units']+=1
    with pytest.raises(AssertionError):validate(broken,complaints,units)
    broken=deepcopy(data);broken['service_repairs'][0]['serial_number']='invalid'
    with pytest.raises(AssertionError):validate(broken,complaints,units)
