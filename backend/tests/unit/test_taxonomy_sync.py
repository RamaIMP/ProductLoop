from copy import deepcopy
import pytest
from app.models.taxonomy import TAXONOMY
from app.services.sync_taxonomy import taxonomy_rows


def test_reference_rows_match_runtime_taxonomy_exactly():
    rows = taxonomy_rows()
    assert len(rows) == len(TAXONOMY['symptoms'])
    assert len({r['symptom'] for r in rows}) == len(rows)
    for row in rows:
        assert row['taxonomy_version'] == str(TAXONOMY['version'])
        info = TAXONOMY['symptoms'][row['symptom']]
        for key in ('issue_type','default_severity','safety','counts_as_complaint','description'):
            assert row[key] == info[key]


def test_invalid_reference_mapping_is_rejected_before_cloud_write():
    taxonomy = deepcopy(TAXONOMY)
    taxonomy['symptoms']['hair_buildup']['issue_type'] = 'invalid'
    with pytest.raises(ValueError):
        taxonomy_rows(taxonomy)
