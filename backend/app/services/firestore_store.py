"""Firestore operational persistence. BigQuery remains the analytics database.

Business operations inherited from LifecycleStore commit records, events and
outbox entries atomically. An optimistic revision guard rejects concurrent writes
instead of silently overwriting them. Background workers still require a single
backend worker/instance; this adapter does not provide a distributed task queue.
"""
import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from fastapi import HTTPException
from google.api_core.exceptions import AlreadyExists, FailedPrecondition
from google.cloud import firestore

from app import config
from app.services.lifecycle import LifecycleStore, complaint_summary


class AtomicWrites:
    """Buffer writes; a revision precondition validates reads at commit time."""
    def __init__(self, store):
        self.store = store
        self.depth = 0

    def __enter__(self):
        if not self.depth:
            self.revision = self.store.meta.get()
            self.values = {}
            self.aborted = False
        self.depth += 1
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.aborted |= exc_type is not None
        self.depth -= 1
        if self.depth or self.aborted or not self.values:
            return False
        batch = self.store.client.batch()
        seq = (self.revision.to_dict() or {}).get('sequence', 0)
        for (kind, key), payload in self.values.items():
            seq += 1
            batch.set(self.store.ref(kind, key), {'payload': payload})
            batch.create(self.store.outbox.document(f'{seq:020d}'), {
                'seq': seq, 'kind': kind, 'id': key, 'payload': payload})
        if len(self.values) > 200:
            raise ValueError('Operational transaction exceeds 200 records')
        if self.revision.exists:
            batch.update(self.store.meta, {'sequence': seq},
                         option=self.store.client.write_option(last_update_time=self.revision.update_time))
        else:
            batch.create(self.store.meta, {'sequence': seq})
        try:
            batch.commit()
        except (AlreadyExists, FailedPrecondition) as error:
            raise HTTPException(409, 'This record changed. Reload and try again.') from error
        return False


class FirestoreLifecycleStore(LifecycleStore):
    def __init__(self, client=None, namespace=None):
        namespace = namespace or os.getenv('PRODUCTLOOP_FIRESTORE_NAMESPACE', 'productloop')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', namespace):
            raise ValueError('Invalid Firestore namespace')
        if client is None and not config.PROJECT_ID:
            raise ValueError('GOOGLE_CLOUD_PROJECT is required for Firestore')
        self.client = client or firestore.Client(project=config.PROJECT_ID,
            database=os.getenv('PRODUCTLOOP_FIRESTORE_DATABASE', '(default)'))
        self.root = self.client.collection('productloop_state').document(namespace)
        self.meta = self.root.collection('metadata').document('revision')
        self.outbox = self.root.collection('outbox')
        self.lock = threading.RLock()
        self.db = AtomicWrites(self)

    def collection(self, kind):
        if kind not in ('complaints', 'registered_units', 'evidence', 'complaint_events'):
            raise ValueError('Unknown lifecycle collection')
        return self.root.collection(kind)

    def ref(self, kind, key):
        # Serial numbers and user-supplied identifiers must never become paths.
        return self.collection(kind).document(sha256(str(key).encode()).hexdigest())

    def get(self, kind, key):
        with self.lock:
            if self.db.depth and (kind, key) in self.db.values:
                return json.loads(self.db.values[kind, key])
            snapshot = self.ref(kind, key).get()
            return json.loads(snapshot.to_dict()['payload']) if snapshot.exists else None

    def all(self, kind):
        with self.lock:
            records = {doc.id: json.loads(doc.to_dict()['payload']) for doc in self.collection(kind).stream()}
            if self.db.depth:
                for (table, key), payload in self.db.values.items():
                    if table == kind:
                        records[self.ref(kind, key).id] = json.loads(payload)
            return list(records.values())

    def put(self, kind, key, value):
        if not self.db.depth:
            raise RuntimeError('Firestore put requires an atomic write context')
        self.collection(kind)
        if kind == 'complaints':
            value = {k: v for k, v in value.items() if k not in ('raw_complaint', 'redacted_complaint')}
            value['complaint_summary'] = complaint_summary(value)
        if self.get(kind, key) != value:
            payload = json.dumps(value)
            if len(payload.encode()) > 900_000:
                raise ValueError('Operational record exceeds Firestore size budget')
            self.db.values[kind, key] = payload

    def save_report(self, record, event_type):
        with self.lock, self.db:
            current = self.get('complaints', record['report_id'])
            if current and current.get('updated_at') != record.get('updated_at'):
                raise HTTPException(409, 'This report changed. Reload and try again.')
            return super().save_report(record, event_type)

    def pending(self, limit=200):
        return [(d['seq'], d['kind'], d['id'], d['payload']) for snapshot in
                self.outbox.order_by('seq').limit(min(limit, 200)).stream()
                for d in [snapshot.to_dict()]]

    def ack(self, sequence):
        # Delete only the successful prefix, leaving concurrently appended writes.
        from google.cloud.firestore_v1.base_query import FieldFilter
        while True:
            docs = list(self.outbox.where(filter=FieldFilter('seq', '<=', sequence)).limit(200).stream())
            if not docs:
                return
            batch = self.client.batch()
            for doc in docs:
                batch.delete(doc.reference)
            batch.commit()

    def sync_status(self):
        result = self.outbox.count().get()
        return {'pending_writes': int(result[0][0].value)}

    def recover_interrupted(self):
        # Another revision can still be completing a recent upload. Never fail
        # fresh jobs simply because a new process started.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        for record in self.all('evidence'):
            if datetime.fromisoformat(record['created_at']) >= cutoff:
                continue
            patch = {}
            if record.get('storage_status') == 'pending':
                patch.update(storage_status='failed', storage_error='Upload interrupted; please upload the file again.')
            if record.get('extraction_status') == 'pending':
                patch['extraction_status'] = 'failed'
            if patch:
                self.evidence_update(record['evidence_id'], patch, 'processing_interrupted')
