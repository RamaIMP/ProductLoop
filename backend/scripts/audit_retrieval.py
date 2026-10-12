"""Read-only live retrieval audit; creates no complaints or cloud records."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models.taxonomy import Extraction
from app.rules.derive import derive
from app.services.retrieval import retrieve_for_report

CASES = [
 ('cleaning','How do I clean hair trapped under my X500 shaving head?','hair_buildup',['x500_man_cleaning']),
 ('noise','My X500 rattles during use even after cleaning. What should I do next?','rattling_sound',['x500_trb_noise_steps','x500_trb_noise_escalate']),
 ('vibration','My X500 shakes and vibrates unusually during use. How can I check it?','increased_vibration',['x500_trb_vibration_steps']),
 ('battery','My X500 battery runs out quickly after a full charge. What can I do?','battery_drains_fast',['x500_trb_battery_steps']),
 ('not_charging','My X500 will not charge. There is no heat, smoke or burning smell. What should I check?','not_charging',['x500_trb_power_steps','x500_man_charging']),
 ('head_fit','My X500 shaving head does not fit securely. What should I check?','head_not_fitting',['x500_trb_fit_steps']),
 ('led','What do the green, amber and red lights on the X500 mean?','led_not_working',['x500_man_led']),
 ('third_party','Can I fit a third-party replacement shaving head on the X500?','blade_replacement_due',['x500_saf_no_diy']),
 ('storage','How should I store my X500 when I will not use it for a month?','storage_question',['x500_man_storage','x500_man_charging']),
 ('warranty','What is the warranty period for the X500?','unclear_description',['x500_svc_warranty']),
 ('kb_gap','Does the X500 have Bluetooth and how do I pair it with my phone?','unclear_description',[]),
 ('safety','My X500 smells burnt while charging. What should I do?','burning_smell',[]),
]


def run(case):
    name, message, symptom, expected = case
    start=perf_counter()
    extraction=Extraction(symptoms=[symptom],confidence=.9,retrieval_query=message)
    classification=derive(extraction.symptoms,extraction.context)
    result=retrieve_for_report(message,extraction,classification)
    ids=[chunk['chunk_id'] for chunk in result['chunks']]
    return {'case':name,'query':message,'expected_ids':expected,
            'expected_hit':bool(set(ids)&set(expected)) if expected else None,
            'mode':result['mode'],'chunks':result['chunks'],
            'elapsed_seconds':round(perf_counter()-start,2)}


if __name__=='__main__':
    results=[]
    with ThreadPoolExecutor(max_workers=1) as pool:
        for result in pool.map(run,CASES):
            results.append(result)
            print(json.dumps({k:v for k,v in result.items() if k!='chunks'}),flush=True)
            print('TOP:',[(c['chunk_id'],round(c['distance'],3)) for c in result['chunks']],flush=True)
    path=Path(__file__).resolve().parents[3]/'output/retrieval-audit-20261012.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(results,indent=2))
    print('Results:',path,flush=True)
