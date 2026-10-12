"""Live development API audit. Uses real configured Gemini calls; writes reproducible evidence."""
import json
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / 'data' / 'test_media'
RUN = datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y%m%d-%H%M%S')
OUT = ROOT / 'test-results' / f'journey-audit-flash-{RUN}'

class Journey:
    def __init__(self, number):
        self.id = number
        self.user = f'audit-{RUN}-{number:02d}'
        self.history = []
        self.extraction = None
        self.report = None
        self.trace = []
        self.checks = []
        self.limits = []
        self.http = httpx.Client(base_url='http://127.0.0.1:8000', timeout=180)

    def call(self, path, payload=None, **kwargs):
        start = time.monotonic()
        r = self.http.post(path, json=payload, **kwargs) if payload is not None else self.http.post(path, **kwargs)
        data = r.json()
        self.trace.append({'path': path, 'input': payload if payload is not None else kwargs.get('data'),
                           'status_code': r.status_code, 'seconds': round(time.monotonic()-start, 2), 'response': data})
        r.raise_for_status()
        return data

    def say(self, message, event='message'):
        r = self.call('/api/conversation', {'user_id': self.user, 'message': message, 'event': event,
            'history': self.history, 'extraction': self.extraction,
            'report_id': self.report['report_id'] if self.report else None})
        if r.get('extraction'): self.extraction = r['extraction']
        if r.get('report'): self.report = r['report']
        self.history.append({'role': 'user', 'text': message})
        if r.get('message'): self.history.append({'role': 'assistant', 'text': r['message']})
        self.check('LLM generated response (or explicit safety fallback)', bool(r.get('message')) or r.get('mode') == 'safety_guardrail')
        return r

    def upload(self, name, message):
        path = MEDIA / name
        mime = {'m4a': 'audio/mp4', 'mp4': 'video/mp4', 'jpg': 'image/jpeg'}[path.suffix[1:]]
        with path.open('rb') as f:
            r = self.call('/api/media/extract', data={'message': message,
                'prior_symptoms_json': json.dumps((self.extraction or {}).get('symptoms', []))},
                files={'file': (f'evidence{path.suffix}', f, mime)})
        self.check('Actual media model, no filename fallback', r['analysis_mode'] == 'multimodal_gemini')
        self.trace[-1]['fixture'] = str(path)
        if r['analysis_mode'] != 'multimodal_gemini':
            raise RuntimeError('Media fallback rejected, matching frontend behavior')
        self.extraction = r['extraction']
        return self.say(message, 'media_added')

    def check(self, name, passed):
        self.checks.append({'check': name, 'passed': bool(passed)})

    def category(self, r, category, severity, safety=False):
        d = r.get('derived') or {}
        self.check(f'Category = {category}', d.get('issue_type') == category)
        self.check(f'Severity = {severity}', d.get('severity') == severity)
        self.check(f'Safety = {safety}', d.get('safety_flag') == safety)
        if safety: self.check('Safety route bypasses post-RAG reasoning', r.get('action') == 'stop_use' and r.get('mode') != 'gemini_reasoning')

    def confirm(self):
        self.report = self.call('/api/reports/confirm', {'user_id': self.user, 'extraction': self.extraction, 'consent_share': True})['report']
        return self.say('I confirmed my report.', 'report_confirmed')

    def listed(self):
        r = self.http.get('/api/reports', params={'user_id': self.user})
        r.raise_for_status()
        self.trace.append({'path': '/api/reports', 'status_code': r.status_code, 'response': r.json()})
        return r.json()


def run(number):
    j = Journey(number)
    try:
        if number == 1:
            j.say('', 'session_start')
            for q in ['Hi', 'How are you?']:
                r = j.say(q); j.check('Greeting does not create extraction/report', not r.get('extraction') and not r.get('report'))
        elif number == 2:
            r = j.say('Who won yesterday’s cricket match?')
            j.check('No incident for unrelated question', not r.get('extraction') and not r.get('report'))
        elif number == 3:
            r = j.say('My shaver is acting weird.')
            j.category(r, 'other_or_unclear', 'low')
            j.check('Clarify rather than confirm', r['action'] == 'continue')
        elif number == 4:
            r = j.say('How should I clean the shaving head?')
            j.category(r, 'cleaning_and_maintenance', 'low')
            j.check('Question intent', j.extraction['user_intent'] == 'ask_question')
            j.check('Post-RAG reasoning answer', r['mode'] == 'gemini_reasoning')
            j.check('No saved complaint', j.listed() == [])
        elif number == 5:
            r = j.say('It sounds louder than before. Started today.')
            j.category(r, 'noise_and_vibration', 'low')
            j.check('Onset retained', j.extraction['context']['onset'] == 'today')
        elif number == 6:
            j.category(j.say('It is louder than before.'), 'noise_and_vibration', 'low')
            r = j.say('I already cleaned it, but it’s still loud.')
            j.category(r, 'noise_and_vibration', 'medium')
            j.check('Persistence retained', j.extraction['context']['persists_after_cleaning'] == 'yes')
        elif number == 7:
            r = j.upload('audio1_rattling_grinding.m4a', 'Please understand the problem from this recording.')
            j.category(r, 'noise_and_vibration', 'medium')
            j.check('Rattling recognised', 'rattling_sound' in j.extraction['symptoms'])
            j.check('No unsupported audio-only observations', not set(j.extraction['symptoms']) & {'burning_smell', 'excessive_heat', 'visible_damage', 'increased_vibration'})
        elif number == 8:
            j.category(j.say('It grinds and the motor gets jammed.'), 'noise_and_vibration', 'high', True)
        elif number == 9:
            r = j.say('It leaves hairs behind and needs several passes.')
            j.category(r, 'shaving_performance', 'low')
            j.check('Both cutting symptoms', {'missed_hairs', 'requires_multiple_passes'} <= set(j.extraction['symptoms']))
        elif number == 10:
            j.category(j.say('It pulls my hair while shaving.'), 'shaving_performance', 'medium')
        elif number == 11:
            j.category(j.say('It won’t charge. There is no heat, smoke, or burning smell.'), 'power_and_charging', 'medium')
        elif number == 12:
            j.category(j.say('A full charge lasts only five minutes. This started last week.'), 'power_and_charging', 'medium')
        elif number == 13:
            j.category(j.say('The head feels loose.'), 'shaving_head_and_fitment', 'medium')
            j.category(j.say('I cleaned and refitted it, but it still won’t lock.'), 'shaving_head_and_fitment', 'high', True)
        elif number == 14:
            r = j.upload('video3_head_detaches.mp4', 'This is what happens. Please understand from the video.')
            j.category(r, 'shaving_head_and_fitment', 'high', True)
            j.check('Head detachment recognised', 'head_detached' in j.extraction['symptoms'])
        elif number == 15:
            j.category(j.say('My shaver burned and smoke came out while charging.'), 'heat_and_safety', 'high', True)
        elif number == 16:
            r = j.say('It feels slightly warm after shaving—not hot, and no smell.')
            j.check('Warmth is not a safety condition', not (r.get('derived') or {}).get('safety_flag'))
            j.check('No excessive heat inferred', 'excessive_heat' not in (j.extraction or {}).get('symptoms', []))
            j.check('No confirmed complaint forced', r['action'] != 'confirm_report')
        elif number == 17:
            j.category(j.upload('image1_hair_buildup_under_head.jpg', 'Please understand from the photo.'), 'cleaning_and_maintenance', 'low')
            r = j.upload('image3_cracked_casing.jpg', 'Here is another photo. Please inspect it too.')
            j.check('Both uploads represented', {'hair_buildup', 'visible_damage'} <= set(j.extraction['symptoms']))
            j.category(r, 'heat_and_safety', 'high', True)
        elif number == 18:
            r = j.say('Can I use a third-party replacement head?')
            j.check('No safety escalation without evidence', not (r.get('derived') or {}).get('safety_flag'))
            j.check('No report automatically created', not r.get('report'))
        elif number in (19, 20):
            j.limits.append('API journey exercised; browser automation unavailable. Home, support visibility, map and Gmail inspected in source only.')
            r = j.say('My shaver rattles. It started today.' if number == 19 else 'The battery drains in five minutes after a full charge.')
            j.check('Review offered', r['action'] == 'confirm_report')
            r = j.confirm()
            j.check('Confirmed report gets reasoning answer', r['mode'] == 'gemini_reasoning')
            report_id = j.report['report_id']
            if number == 19:
                r = j.say('That fixed it.')
                j.check('Resolved on same report', j.report['report_id'] == report_id and j.report['status'] == 'resolved')
            else:
                r = j.say('Still not fixed.')
                j.check('Ticket confirmation offered', r['action'] == 'ticket_confirm')
                r = j.say('Create a ticket.')
                j.check('Ticket raised on same report', j.report['report_id'] == report_id and j.report['status'] == 'ticket_raised')
                j.report = j.call(f'/api/reports/{report_id}/callback', {'slot': 'Tomorrow · 10:00–10:30 AM'})
                j.check('Callback saved', j.report['callback']['slot'] == 'Tomorrow · 10:00–10:30 AM')
                j.say('Tomorrow · 10:00–10:30 AM', 'callback_requested')
            reports = j.listed()
            j.check('Incident remains listed once', len(reports) == 1 and reports[0]['report_id'] == report_id)
    except Exception as e:
        j.checks.append({'check': 'Execution completed', 'passed': False, 'error': str(e)})
    finally:
        j.http.close()
    result = {'case': number, 'user_id': j.user, 'checks': j.checks, 'limitations': j.limits, 'trace': j.trace}
    result['automated_status'] = 'FAIL' if any(not c['passed'] for c in j.checks) else 'PARTIAL' if j.limits else 'PASS'
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'case-{number:02d}.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f'Case {number:02d}: {result["automated_status"]}', flush=True)
    return result


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    print('Evidence:', OUT, flush=True)
    inventory = []
    for folder in (MEDIA, ROOT.parent / 'Data_v2' / 'test_media'):
        for p in sorted(folder.iterdir()):
            if p.suffix in ('.jpg', '.m4a', '.mp4'):
                inventory.append({'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
    (OUT / 'media-inventory.json').write_text(json.dumps(inventory, indent=2))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in as_completed([pool.submit(run, n) for n in range(1, 21)])]
    (OUT / 'results.json').write_text(json.dumps(sorted(results, key=lambda r: r['case']), indent=2, ensure_ascii=False))
    print('Evidence:', OUT, flush=True)
