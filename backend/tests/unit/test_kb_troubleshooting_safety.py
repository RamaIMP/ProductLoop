from app.services.load_kb_embeddings import prepare


def test_head_procedures_include_isolation_and_drying():
    rows = {r['chunk_id']: r['content'].lower() for r in prepare()}
    for topic in ('noise', 'vibration', 'fit', 'cutting', 'heat'):
        text = rows[f'x500_trb_{topic}_steps']
        assert 'switch off the shaver and disconnect it from charging' in text
        if topic != 'fit':
            assert 'air dry completely before reassembling' in text
            assert 'at least 30 minutes' in text


def test_charging_procedures_include_port_check_and_disconnection():
    rows = {r['chunk_id']: r['content'].lower() for r in prepare()}
    for topic in ('noise', 'battery', 'power', 'heat'):
        text = rows[f'x500_trb_{topic}_steps']
        assert 'inspect the charging port for moisture, liquid or visible damage' in text
        assert 'disconnect the charging cable before' in text


def test_all_troubleshooting_chunks_have_stop_use_precautions():
    for row in prepare():
        if row['document_type'] == 'troubleshooting_guide':
            text = row['content'].lower()
            assert 'burning smell' in text, row['chunk_id']
            assert 'do not' in text and 'service centre' in text, row['chunk_id']


def test_battery_escalation_preserves_or_condition():
    row = next(r for r in prepare() if r['chunk_id'] == 'x500_trb_battery_escalate')
    assert 'fewer than 20 minutes after a confirmed full charge, or the device is less than 12 months old' in row['content']


def test_heat_guidance_does_not_treat_cooling_as_hazard_clearance():
    row = next(r for r in prepare() if r['chunk_id'] == 'x500_trb_heat_steps')
    assert 'cooling is not permission to retest a hazardous device' in row['content']
