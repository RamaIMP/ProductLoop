"""Durable single-process development state and ordered BigQuery outbox.

SQLite contains structured metadata only, never media bytes. Use a managed
operational database/outbox before running multiple backend replicas.
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException

def now():
    return datetime.now(timezone.utc).isoformat()

def complaint_summary(record):
    """Summarize structured findings, never copy conversational filler or raw text."""
    extraction = record.get('extraction') or {}
    symptoms = extraction.get('symptoms') or record.get('symptoms') or []
    if not symptoms:
        return None
    parts = ['Reported findings: ' + ', '.join(dict.fromkeys(s.replace('_', ' ') for s in symptoms)) + '.']
    context = extraction.get('context') or record.get('context') or {}
    onset = {'today':'today', 'this_week':'this week', 'longer':'longer ago'}.get(context.get('onset'))
    if onset:
        parts.append('Started ' + onset + '.')
    cleaning = {'yes':'Issue persists after cleaning.', 'no':'Issue improved after cleaning.',
        'not_tried':'Cleaning has not been reported as tried.'}.get(context.get('persists_after_cleaning'))
    if cleaning:
        parts.append(cleaning)
    if context.get('during_charging') is True:
        parts.append('Occurs during charging.')
    outcome = record.get('outcome') or record.get('guidance_outcome')
    if record.get('status') == 'resolved':
        parts.append('User marked the issue resolved.')
    elif outcome == 'not_fixed':
        parts.append('User reports the issue is not fixed.')
    if record.get('ticket_id'):
        parts.append('Support ticket raised.')
    return ' '.join(parts)

class LifecycleStore:
    def __init__(self, path):
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS records (
              kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
              PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS outbox (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
              id TEXT NOT NULL, payload TEXT NOT NULL);
        """)
        self.lock = threading.RLock()

    def get(self, kind, key):
        with self.lock:
            row = self.db.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind, key)).fetchone()
            return json.loads(row[0]) if row else None

    def all(self, kind):
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM records WHERE kind=? ORDER BY rowid', (kind,))]

    def put(self, kind, key, value):
        # Called inside lock + transaction so state and outbox commit together.
        if kind == 'complaints':
            value = {k:v for k,v in value.items() if k not in ('raw_complaint','redacted_complaint')}
            value['complaint_summary'] = complaint_summary(value)
        payload = json.dumps(value)
        previous = self.db.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind,key)).fetchone()
        if previous and previous[0] == payload:
            return
        self.db.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload', (kind,key,payload))
        self.db.execute('INSERT INTO outbox(kind,id,payload) VALUES(?,?,?)', (kind,key,payload))

    def event(self, complaint_id, event_type, before=None, after=None, evidence_id=None, details=None):
        event_id = 'evt_' + uuid4().hex
        def classification(record):
            d = (record or {}).get('derived') or {}
            return {k: d.get(k) for k in ('issue_type','severity','safety_flag')} if d else None
        self.put('complaint_events', event_id, {
            'event_id':event_id, 'complaint_id':complaint_id, 'evidence_id':evidence_id,
            'occurred_at':now(), 'event_type':event_type,
            'previous_status':(before or {}).get('status'), 'new_status':(after or {}).get('status'),
            'previous_classification':classification(before), 'new_classification':classification(after),
            'actor_type':'system', 'details':details or {}})

    def incident(self, complaint_id, user_id):
        record = self.get('complaints', complaint_id)
        if not record or record['user_id'] != user_id:
            raise HTTPException(404, 'Incident not found')
        return record

    def draft(self, user_id, complaint_id=None, serial_number=None, location=None):
        complaint_id = complaint_id or 'PL-' + uuid4().hex
        with self.lock, self.db:
            existing = self.get('complaints', complaint_id)
            if existing:
                existing = self.incident(complaint_id, user_id)
                if serial_number and existing.get('serial_number') != serial_number:
                    raise HTTPException(409, 'This incident already belongs to a different device. Start a new report.')
                return existing
            if not serial_number:
                # Single-device consumer flow: inherit only an unambiguous owned X500.
                candidates = [u for u in self.all('registered_units')
                    if u.get('consumer_id') == user_id
                    and (u.get('product_model') or '').strip().upper() == 'X500']
                if len(candidates) == 1:
                    serial_number = candidates[0]['serial_number']
            unit = self.get('registered_units', serial_number) if serial_number else None
            if serial_number and (not unit or unit['consumer_id'] != user_id):
                raise HTTPException(409, 'Register this product before linking it to an incident.')
            if unit and (unit.get('product_model') or '').strip().upper() != 'X500':
                raise HTTPException(409, 'Troubleshooting for this model is not available until its knowledge base is connected.')
            record = {'report_id':complaint_id, 'user_id':user_id, 'created_at':now(),
                'updated_at':now(), 'status':'draft', 'consent_share':False,
                'serial_number':serial_number, 'unit_id':unit.get('unit_id') if unit else None,
                'batch_reference':unit.get('batch_id') if unit else None,
                'region':unit.get('region') if unit else None, 'product_model':unit.get('product_model') if unit else 'X500',
                'input_types':[], 'complaint_summary':None, **(location or {})}
            self.put('complaints', complaint_id, record)
            self.event(complaint_id, 'incident_started', after=record)
            return record

    def register(self, record):
        serial = record['serial_number']
        with self.lock, self.db:
            previous = self.get('registered_units', serial)
            if previous:
                if previous['consumer_id'] != record['consumer_id']:
                    raise HTTPException(409, 'Product is already registered.')
                if previous.get('product_model') != record.get('product_model'):
                    raise HTTPException(409, 'This serial number is already registered with a different model.')
                return previous
            record = {**record, 'unit_id':'unit_' + uuid4().hex, 'registered_at':now()}
            self.put('registered_units', serial, record)
            return record

    def classify(self, complaint_id, user_id, extraction, derived, message='', input_type='text'):
        with self.lock, self.db:
            before = self.incident(complaint_id,user_id)
            record = {**before, 'extraction':extraction, 'derived':derived}
            record.pop('raw_complaint', None)
            record.pop('redacted_complaint', None)
            record['complaint_summary'] = complaint_summary(record)
            record['input_types'] = list(dict.fromkeys([*record.get('input_types',[]), input_type]))
            if record == before:
                return record
            record['updated_at'] = now()
            self.put('complaints',complaint_id,record)
            if before.get('derived') != derived:
                self.event(complaint_id,'classification_changed',before,record)
            return record

    def save_report(self, record, event_type):
        with self.lock, self.db:
            before = self.get('complaints', record['report_id'])
            if before == record:
                return record
            record = {k:v for k,v in record.items() if k not in ('raw_complaint','redacted_complaint')}
            record = {**record, 'updated_at':now(), 'complaint_summary':complaint_summary(record)}
            self.put('complaints',record['report_id'],record)
            self.event(record['report_id'],event_type,before,record)
            return record

    def evidence_start(self, evidence_id, complaint_id, user_id, filename, mime):
        with self.lock, self.db:
            incident = self.incident(complaint_id,user_id)
            record = {'evidence_id':evidence_id, 'complaint_id':complaint_id,
                'consumer_id':user_id, 'kind':{'image':'photo','audio':'audio','video':'video'}[mime.split('/')[0]],
                'original_filename':filename, 'content_type':mime, 'created_at':now(),
                'storage_status':'pending', 'extraction_status':'pending',
                'consent_share':incident.get('consent_share',False)}
            self.put('evidence',evidence_id,record)
            self.event(complaint_id,'evidence_added',evidence_id=evidence_id)
            return record

    def evidence_update(self, evidence_id, patch, event_type):
        with self.lock, self.db:
            before = self.get('evidence',evidence_id)
            if not before:
                raise HTTPException(404,'Evidence not found')
            record = {**before, **patch}
            if record == before:
                return record
            self.put('evidence',evidence_id,record)
            self.event(record['complaint_id'],event_type,evidence_id=evidence_id)
            return record

    def pending(self, limit=200):
        with self.lock:
            return list(self.db.execute('SELECT seq,kind,id,payload FROM outbox ORDER BY seq LIMIT ?', (limit,)))

    def ack(self, sequence):
        with self.lock, self.db:
            self.db.execute('DELETE FROM outbox WHERE seq<=?', (sequence,))

    def sync_status(self):
        with self.lock:
            return {'pending_writes':self.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]}

    def recover_interrupted(self):
        for record in self.all('evidence'):
            patch = {}
            if record['storage_status'] == 'pending':
                patch.update(storage_status='failed', storage_error='Server restarted before upload completion; re-upload required.')
            if record['extraction_status'] == 'pending':
                patch.update(extraction_status='failed')
            if patch:
                self.evidence_update(record['evidence_id'],patch,'processing_interrupted')

_store = None
def get_store():
    global _store
    if _store is None:
        backend = os.getenv('PRODUCTLOOP_STATE_BACKEND', 'sqlite').strip().lower()
        if backend == 'firestore':
            from app.services.firestore_store import FirestoreLifecycleStore
            _store = FirestoreLifecycleStore()
        elif backend == 'sqlite':
            path = os.getenv('PRODUCTLOOP_STATE_DB') or str(Path(__file__).resolve().parents[3] / '.runtime' / 'lifecycle.sqlite3')
            _store = LifecycleStore(path)
        else:
            raise ValueError('PRODUCTLOOP_STATE_BACKEND must be sqlite or firestore')
    return _store

def complaint_row(record):
    from app.models.taxonomy import SYMPTOM_INFO
    extraction = record.get('extraction') or {}
    derived = record.get('derived') or {}
    submitted = bool(record.get('submitted_at'))
    return {
        **{k:v for k,v in record.items() if k not in ('report_id','user_id','extraction','derived','outcome')},
        'complaint_id':record['report_id'], 'consumer_id':record['user_id'],
        **{k:extraction.get(k) for k in ('user_intent','symptoms','context','confidence')},
        'product_model':extraction.get('product_model') or record.get('product_model','X500'),
        **derived,
        'complaint_summary':complaint_summary(record),
        # Clear deprecated columns on existing cloud rows; never retain raw text.
        'raw_complaint':None, 'redacted_complaint':None,
        'counts_as_complaint':submitted and extraction.get('user_intent') == 'report_problem' and any(
            SYMPTOM_INFO.get(symptom,{}).get('counts_as_complaint',False) for symptom in extraction.get('symptoms',[])),
        'guidance_outcome':record.get('outcome')}
