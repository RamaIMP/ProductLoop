"""Run live model grounding regression checks without restarting the running API.

Run from backend: .venv/bin/python ../scripts/check_grounding.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.models.taxonomy import Extraction
from app.rules.derive import derive
from app.services.gemini import reason_over_retrieval
from app.services.retrieval import retrieve_for_report

cases = [
    ('third_party', 'Can I use a third-party replacement head?', 'blade_replacement_due', False),
    ('paraphrase', 'Will a replacement head from another brand fit my X500?', 'blade_replacement_due', False),
    ('warranty', 'Does fitting another brand of head void my warranty?', 'blade_replacement_due', False),
    ('cleaning', 'How should I clean the shaving head?', 'hair_buildup', True),
    ('charging', 'My shaver will not charge. What should I check?', 'not_charging', True),
    ('empty', 'Can I use a third-party replacement head?', 'blade_replacement_due', False),
]
results = []
for name, question, symptom, expect_sources in cases:
    extraction = Extraction(symptoms=[symptom], user_intent='ask_question', confidence=0.9)
    derived = derive(extraction.symptoms, extraction.context, extraction.user_intent.value)
    retrieval = retrieve_for_report(question, extraction, derived)
    if name == 'empty':
        retrieval['chunks'] = []
    row = {'case': name, 'question': question, 'retrieval': retrieval}
    try:
        answer = reason_over_retrieval(message=question, history=[], extraction=extraction,
                                      derived=derived.model_dump(mode='json'), retrieval=retrieval)
        row['answer'] = answer.model_dump()
        row['citation_check_passed'] = bool(answer.source_ids) == expect_sources
    except Exception as exc:
        row['error'] = str(exc)
    results.append(row)
    print(json.dumps(row, ensure_ascii=False), flush=True)
out = Path(__file__).resolve().parents[1] / 'test-results' / ('grounding-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.json')
out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
print('Evidence:', out)
if any('error' in row or not row.get('citation_check_passed') for row in results):
    sys.exit(1)
