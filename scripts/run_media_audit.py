"""Supplementary extraction-only checks, using the provided fixture answer key."""
import json
import sys
import time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / 'data' / 'test_media'
OUT = Path(sys.argv[1])
results = []
with httpx.Client(base_url='http://127.0.0.1:8000', timeout=180) as client:
    for case in json.loads((MEDIA / 'answer_key.json').read_text())['cases']:
        path = MEDIA / case['file']
        start = time.monotonic()
        item = {'file': str(path), 'input': case['message_to_send'], 'expected': case['expected']}
        try:
            mime = {'.m4a': 'audio/mp4', '.mp4': 'video/mp4', '.jpg': 'image/jpeg'}[path.suffix]
            with path.open('rb') as f:
                response = client.post('/api/media/extract', data={'message': case['message_to_send'], 'prior_symptoms_json': '[]'},
                    files={'file': ('evidence' + path.suffix, f, mime)})
            item.update(status_code=response.status_code, response=response.json())
            response.raise_for_status()
            r = response.json()
            syms = set(r['media_extraction']['symptoms'])
            exp = case['expected']
            failures = []
            if r['analysis_mode'] != 'multimodal_gemini': failures.append('Not a real media-model result')
            missing = set(exp['must_have_symptoms']) - syms
            forbidden = syms & set(exp['must_not_have_symptoms'])
            if missing: failures.append('Missing required symptoms: ' + ', '.join(sorted(missing)))
            if forbidden: failures.append('Unsupported symptoms: ' + ', '.join(sorted(forbidden)))
            for key, value in exp['derived'].items():
                if r['derived'][key] != value: failures.append(f'{key}: expected {value}, got {r["derived"][key]}')
            item['failures'] = failures
            item['context_differences'] = {key: {'expected': value, 'actual': r['media_extraction']['context'][key]}
                for key, value in exp['context'].items() if r['media_extraction']['context'][key] != value}
            item['status'] = 'FAIL' if failures else 'PASS'
        except Exception as e:
            item.update(status='FAIL', error=str(e))
        item['seconds'] = round(time.monotonic()-start, 2)
        results.append(item)
        (OUT / 'media-results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(path.name, item['status'], flush=True)
