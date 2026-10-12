import pytest

from app.services.load_kb_embeddings import DIMENSIONS, prepare, validate_vector


def test_source_has_unique_traceable_draft_chunks():
    rows = prepare()
    assert len(rows) == len({r['chunk_id'] for r in rows}) == 41
    assert all(r['review_status'] == 'draft' and r['source_file'] and r['content_hash'] for r in rows)
    assert next(r for r in rows if r['chunk_id'] == 'x500_svc_fit')['audience'] == 'technician'
    assert all('embedding' not in r for r in rows)


@pytest.mark.parametrize('values', [[1.0], [0.0] * DIMENSIONS, [float('nan')] * DIMENSIONS,
                                  [float('inf')] * DIMENSIONS])
def test_invalid_vectors_are_rejected(values):
    with pytest.raises(ValueError):
        validate_vector(values)


def test_valid_vector():
    validate_vector([0.01] * DIMENSIONS)


def test_corrected_cleaning_starts_with_power_precaution():
    row = next(r for r in prepare() if r['chunk_id'] == 'x500_man_cleaning')
    assert row['content'].startswith('Before cleaning, switch off the shaver and disconnect it from charging.')
    assert 'Do not use the shaver if the head cannot be secured.' in row['content']


def test_power_guidance_checks_hazards_before_charging_and_disconnects_before_use():
    row = next(r for r in prepare() if r['chunk_id'] == 'x500_trb_power_steps')
    content = row['content']
    assert content.index('inspect the charging port for moisture') < content.index('charge for 5 minutes')
    assert 'disconnect the charging cable before attempting to switch on' in content
    assert 'Never operate it while charging.' in content
