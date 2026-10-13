"""Live-model freeze audit. Isolated SQLite; read-only BigQuery RAG; local media archive.

No application changes and no writes to demo BigQuery/GCS. Run from backend.
"""
import json
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from time import perf_counter
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.main import app
from app import config
from app.services import lifecycle, media_jobs
from app.api import consumer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'test-results' / ('freeze-audit-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
OUT.mkdir(parents=True)
lifecycle._store = lifecycle.LifecycleStore(':memory:')
config.MEDIA_BUCKET = ''


@asynccontextmanager
async def isolated_lifespan(_):
    yield
    await media_jobs.finish_uploads()


app.router.lifespan_context = isolated_lifespan


class Journey:
    def __init__(self, client, name):
        self.client, self.name, self.trace, self.checks = client, name, [], []
        self.user = 'freeze-audit-' + name
        self.cid = None
        self.report = None
        self.extraction = None
        self.history = []

    def check(self, label, condition):
        self.checks.append({'check': label, 'passed': bool(condition)})

    def call(self, path, payload=None, **kwargs):
        started = perf_counter()
        r = self.client.post(path, json=payload, **kwargs) if payload is not None else self.client.post(path, **kwargs)
        data = r.json()
        self.trace.append({'path': path, 'input': payload or kwargs.get('data'), 'status': r.status_code,
            'seconds': round(perf_counter()-started, 2), 'response': data})
        r.raise_for_status()
        return data

    def say(self, message, event='message'):
        result = self.call('/api/conversation', {'user_id': self.user, 'complaint_id': self.cid,
            'report_id': self.report['report_id'] if self.report else None,
            'extraction': self.extraction, 'history': self.history, 'message': message, 'event': event, 'debug': True})
        self.cid = result.get('complaint_id') or self.cid
        self.extraction = result.get('extraction') or self.extraction
        self.report = result.get('report') or self.report
        self.history.append({'role': 'user', 'text': message})
        if result.get('message'): self.history.append({'role': 'assistant', 'text': result['message']})
        return result

    def category(self, r, issue, safety=False):
        self.check('Issue type: '+issue, (r.get('derived') or {}).get('issue_type') == issue)
        self.check('Safety flag: '+str(safety), (r.get('derived') or {}).get('safety_flag') == safety)

    def upload(self, filename, purpose='general'):
        if not self.cid:
            self.cid = self.call('/api/incidents', {'user_id': self.user, 'complaint_id': 'PL-'+str(uuid4())})['report_id']
        path = ROOT / 'data/test_media' / filename
        mime = {'.jpg': 'image/jpeg', '.mp4':'video/mp4', '.m4a':'audio/mp4'}[path.suffix]
        with path.open('rb') as stream:
            result = self.call('/api/media/extract', data={'user_id':self.user, 'complaint_id':self.cid,
                'audio_purpose':purpose, 'message':'Please understand the issue from this file.',
                'prior_symptoms_json':json.dumps((self.extraction or {}).get('symptoms',[])), 'debug':'true'},
                files={'file':('evidence'+path.suffix, stream, mime)})
        self.extraction = result['extraction']
        self.check('Actual multimodal analysis', result['analysis_mode'] == 'multimodal_gemini')
        return result

    def confirm(self):
        self.report = self.call('/api/reports/confirm', {'user_id': self.user, 'complaint_id': self.cid,
            'extraction': self.extraction, 'consent_share':False})['report']
        self.cid = self.report['report_id']


def run_case(client, name, fn):
    j = Journey(client, name)
    try:
        fn(j)
    except Exception as exc:
        j.checks.append({'check':'Execution completed', 'passed':False, 'error':str(exc)})
    result = {'case':name, 'status':'PASS' if j.checks and all(c['passed'] for c in j.checks) else 'FAIL',
              'checks':j.checks, 'trace':j.trace}
    (OUT / (name+'.json')).write_text(json.dumps(result, indent=2))
    print(name, result['status'], [c for c in j.checks if not c['passed']], flush=True)
    return result


def text_case(message, issue, safety=False):
    return lambda j: j.category(j.say(message), issue, safety)


def greetings(j):
    for text in ['', 'hi', 'hello', 'good morning', 'how are you?']:
        r = j.say(text, 'session_start' if not text else 'message')
        j.check('Greeting without complaint: '+text, bool(r.get('message')) and not r.get('extraction') and not r.get('report'))


def vague(j):
    r = j.say('I have an issue with my shaver.')
    j.check('Vague issue asks for details', r['action'] == 'continue' and bool(r.get('message')))


def correction(j, ambiguous=False, conflicting=False):
    if conflicting:
        j.upload('image3_cracked_casing.jpg')
        msg = 'Sorry, I made a typo. There is no cracked casing or visible damage. It only rattles.'
    else:
        j.say('There is a burning smell.')
        if ambiguous:
            r = j.say('Sorry, it was a typo.')
            j.check('Ambiguous typo asks and retains safety', r['derived']['safety_flag'] and bool(r.get('message')))
        msg = 'There is no burning smell. My earlier statement was a typo. It only rattles.'
    r = j.say(msg)
    j.check('Safety after correction', r['derived']['safety_flag'] == conflicting)
    if conflicting:
        j.check('Media conflict asks for clarification', bool(r.get('message')))
    else:
        j.check('Retracted symptom removed', 'burning_smell' not in r['extraction']['symptoms'])


def guidance(j, message):
    r = j.say(message)
    j.check('Cited Flash-Lite response', r['mode'] == 'gemini_reasoning' and bool(r['sources']))


def lifecycle_case(j, resolved):
    j.say('My shaver rattles. It started today.')
    j.confirm()
    r = j.say('I confirmed my report.', 'report_confirmed')
    j.check('Guidance after confirmation', r['mode'] == 'gemini_reasoning' and bool(r.get('sources')))
    if resolved:
        r = j.say('That fixed it.', 'resolved')
        j.check('Resolved on same ID', r['report']['status'] == 'resolved' and r['report']['report_id'] == j.cid)
    else:
        j.say('Still not fixed.', 'not_resolved')
        r = j.say('Create ticket', 'create_ticket')
        ticket = r['report']['ticket_id']
        r = j.say('Create ticket', 'create_ticket')
        j.check('Ticket idempotent', r['report']['ticket_id'] == ticket)
        slots = j.client.get('/api/callback-slots').json()
        slot = slots[0]
        j.call(f'/api/reports/{j.cid}/callback', {'user_id':j.user, 'slot':slot['label'],
            **{k:slot[k] for k in ('scheduled_start','scheduled_end','time_zone')}})
        j.check('Callback persisted', bool(lifecycle.get_store().incident(j.cid,j.user).get('callback')))
    reports = j.client.get('/api/reports', params={'user_id':j.user}).json()
    j.check('One visible report', len(reports)==1 and reports[0]['report_id']==j.cid)


def safety_booking(j):
    j.say('My shaver smells burnt while charging.')
    j.confirm()
    slots = j.client.get('/api/callback-slots').json()
    payload = {'user_id':j.user, 'centre_id':'central', 'scheduled_start':slots[0]['scheduled_start']}
    booking = j.call(f'/api/reports/{j.cid}/service-appointment', payload)
    again = j.call(f'/api/reports/{j.cid}/service-appointment', payload)
    j.check('Safety appointment linked and idempotent', booking['complaint_id']==j.cid and booking['booking_id']==again['booking_id'])


def media(j, filename, required, purpose='general', forbidden=()):
    r = j.upload(filename, purpose)
    symptoms = set(r['media_extraction']['symptoms'])
    j.check('Expected symptoms: '+str(required), set(required) <= symptoms)
    j.check('No unsupported symptoms', not symptoms.intersection(forbidden))
    if purpose == 'spoken_complaint':
        j.check('Speech understood', (r['media_extraction'].get('speech') or {}).get('status') == 'understood')


def multiple_media(j):
    j.upload('image1_hair_buildup_under_head.jpg')
    r = j.upload('image3_cracked_casing.jpg')
    j.check('Both evidence items retained', {'hair_buildup','visible_damage'} <= set(r['extraction']['symptoms']))
    j.check('Safety damage detected', r['derived']['safety_flag'])


CASES = [
 ('01-greetings', greetings), ('02-vague', vague),
 ('03-noise', text_case('It rattles while shaving. Started today.', 'noise_and_vibration')),
 ('04-vibration', text_case('The shaver vibrates much more than before.', 'noise_and_vibration')),
 ('05-charging-negation', text_case('It will not charge. There is no heat, smoke, or burning smell.', 'power_and_charging')),
 ('06-battery', text_case('A full charge lasts only five minutes.', 'power_and_charging')),
 ('07-hair-buildup', text_case('Hair is stuck under the shaving head.', 'cleaning_and_maintenance')),
 ('08-head-fit', text_case('The replacement head does not fit.', 'shaving_head_and_fitment')),
 ('09-burning', text_case('There is a burning smell while charging.', 'heat_and_safety', True)),
 ('10-sparks', text_case('Sparks came out of the charger.', 'heat_and_safety', True)),
 ('11-jammed', text_case('It grinds and the motor is jammed.', 'noise_and_vibration', True)),
 ('12-cleaning-guidance', lambda j: guidance(j,'How do I clean hair trapped under the shaving head?')),
 ('13-battery-guidance', lambda j: guidance(j,'What should I check when the X500 battery drains quickly?')),
 ('14-third-party', lambda j: guidance(j,'Can I use a third-party replacement head?')),
 ('15-explicit-correction', correction),
 ('16-vague-then-correction', lambda j: correction(j,ambiguous=True)),
 ('17-media-conflict-correction', lambda j: correction(j,conflicting=True)),
 ('18-resolved', lambda j: lifecycle_case(j,True)),
 ('19-ticket-callback', lambda j: lifecycle_case(j,False)),
 ('20-safety-booking', safety_booking),
 ('21-hair-photo', lambda j: media(j,'image1_hair_buildup_under_head.jpg',['hair_buildup'])),
 ('22-cracked-photo', lambda j: media(j,'image3_cracked_casing.jpg',['visible_damage'])),
 ('23-rattling-audio', lambda j: media(j,'audio1_rattling_grinding.m4a',['rattling_sound'],'device_sound',('burning_smell','excessive_heat','visible_damage'))),
 ('24-spoken-hazard', lambda j: media(j,'audio2_spoken_burnt_smell.m4a',['burning_smell'],'spoken_complaint')),
 ('25-head-detaches-video', lambda j: media(j,'video3_head_detaches.mp4',['head_detached'])),
 ('26-charging-video', lambda j: media(j,'video2_charging_led_off.mp4',['led_not_working'])),
 ('27-multiple-photos', multiple_media),
]

if __name__ == '__main__':
    print('Results:', OUT, flush=True)
    print('Models:',config.MODEL_CHAT,config.MODEL_REASON,'RAG:',config.RAG_MODE,flush=True)
    with TestClient(app) as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            selected = [pair for pair in CASES if not sys.argv[1:] or pair[0] in sys.argv[1:]]
            results = list(pool.map(lambda pair: run_case(client,*pair), selected))
    (OUT/'results.json').write_text(json.dumps(results,indent=2))
    print('PASS',sum(r['status']=='PASS' for r in results),'/',len(results),flush=True)
