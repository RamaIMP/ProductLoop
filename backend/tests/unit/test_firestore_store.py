"""Adapter contract tests with a deterministic Firestore double; no cloud writes."""
from copy import copy, deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from google.api_core.exceptions import AlreadyExists, FailedPrecondition

from app.services import lifecycle
from app.services.firestore_store import FirestoreLifecycleStore


class Reference:
    def __init__(self, client, path):
        self.client, self.path = client, path
        self.id = path[-1]

    def collection(self, name):
        return Collection(self.client, self.path + (name,))

    def get(self):
        entry = self.client.data.get(self.path)
        value = deepcopy(entry[1]) if entry else None
        return SimpleNamespace(exists=entry is not None, update_time=entry[0] if entry else None,
                               id=self.id, reference=self, to_dict=lambda: value)


class Collection:
    def __init__(self, client, path):
        self.client, self.path = client, path
        self.cap, self.filter, self.order = 10_000, None, None

    def document(self, name):
        return Reference(self.client, self.path + (name,))

    def stream(self):
        docs = [Reference(self.client, path).get() for path in self.client.data
                if path[:-1] == self.path]
        if self.filter:
            docs = [d for d in docs if d.to_dict()[self.filter.field_path] <= self.filter.value]
        if self.order:
            docs.sort(key=lambda d: d.to_dict()[self.order])
        return iter(docs[:self.cap])

    def order_by(self, field):
        query = copy(self)
        query.order = field
        return query

    def where(self, *, filter):
        query = copy(self)
        query.filter = filter
        return query

    def limit(self, cap):
        query = copy(self)
        query.cap = cap
        return query

    def count(self):
        return SimpleNamespace(get=lambda: [[SimpleNamespace(value=len(list(self.stream())))]])


class Batch:
    def __init__(self, client):
        self.client, self.ops = client, []

    def set(self, ref, value):
        self.ops.append(('set', ref, value, None))

    def create(self, ref, value):
        self.ops.append(('create', ref, value, None))

    def update(self, ref, value, option):
        self.ops.append(('update', ref, value, option))

    def delete(self, ref):
        self.ops.append(('delete', ref, None, None))

    def commit(self):
        if self.client.fail:
            raise RuntimeError('Unavailable')
        data = deepcopy(self.client.data)
        for op, ref, value, option in self.ops:
            if op == 'create' and ref.path in data:
                raise AlreadyExists('Conflict')
            if op == 'update' and (ref.path not in data or data[ref.path][0] != option):
                raise FailedPrecondition('Conflict')
            if op == 'delete':
                data.pop(ref.path, None)
            else:
                data[ref.path] = (self.client.version + 1, deepcopy(value))
        self.client.version += 1
        self.client.data = data


class FakeClient:
    def __init__(self):
        self.data, self.version, self.fail = {}, 0, False

    def collection(self, name):
        return Collection(self, (name,))

    def batch(self):
        return Batch(self)

    def write_option(self, *, last_update_time):
        return last_update_time


@pytest.fixture
def store():
    return FirestoreLifecycleStore(FakeClient(), namespace='test')


def test_lifecycle_survives_new_store_instance(store):
    unit = store.register({'serial_number': 'X/500', 'consumer_id': 'u', 'product_model': 'X500'})
    report = store.draft('u', 'incident')
    assert report['unit_id'] == unit['unit_id']
    report.update(submitted_at=lifecycle.now(), status='awaiting_feedback')
    store.save_report(report, 'submitted')
    store.evidence_start('ev1', 'incident', 'u', 'photo.jpg', 'image/jpeg')
    store.evidence_update('ev1', {'storage_status': 'stored', 'storage_uri': 'gs://test/photo'}, 'stored')
    restarted = FirestoreLifecycleStore(store.client, namespace='test')
    assert restarted.incident('incident', 'u')['status'] == 'awaiting_feedback'
    assert restarted.get('evidence', 'ev1')['storage_status'] == 'stored'
    assert len(restarted.all('complaint_events')) == 4
    pending = restarted.pending()
    assert pending and pending == sorted(pending)
    restarted.ack(pending[1][0])
    assert restarted.pending() == pending[2:]
    assert restarted.sync_status()['pending_writes'] == len(pending) - 2


def test_failed_commit_writes_neither_record_nor_event_nor_outbox(store):
    store.client.fail = True
    with pytest.raises(RuntimeError):
        store.draft('u', 'incident')
    assert not store.client.data
    store.client.fail = False
    assert store.draft('u', 'incident')['report_id'] == 'incident'


def test_exception_rolls_back_nested_operation(store):
    with pytest.raises(ValueError):
        with store.lock, store.db:
            store.draft('u', 'incident')
            raise ValueError('abort')
    assert store.get('complaints', 'incident') is None
    assert store.pending() == []


def test_concurrent_commit_rejected_without_partial_writes(store):
    other = FirestoreLifecycleStore(store.client, namespace='test')
    with pytest.raises(HTTPException) as error:
        with store.lock, store.db:
            store.draft('u', 'first')
            other.draft('u', 'second')
    assert error.value.status_code == 409
    assert store.get('complaints', 'first') is None
    assert store.get('complaints', 'second')


def test_stale_report_cannot_overwrite_newer_status(store):
    record = store.draft('u', 'incident')
    stale = dict(record)
    record['status'] = 'resolved'
    store.save_report(record, 'resolved')
    stale['status'] = 'ticket_raised'
    with pytest.raises(HTTPException):
        store.save_report(stale, 'ticket_raised')
    assert store.get('complaints', 'incident')['status'] == 'resolved'


def test_fresh_media_jobs_not_failed_on_startup(store):
    store.draft('u', 'incident')
    store.evidence_start('e', 'incident', 'u', 'photo.jpg', 'image/jpeg')
    store.recover_interrupted()
    assert store.get('evidence', 'e')['extraction_status'] == 'pending'


def test_report_lookup_does_not_require_memory_cache(store, monkeypatch):
    from app.api.consumer import _saved_report, save_outcome, OutcomeRequest
    monkeypatch.setattr(lifecycle, '_store', store)
    record = store.draft('u', 'incident')
    record.update(submitted_at=lifecycle.now(), status='awaiting_feedback')
    store.save_report(record, 'submitted')
    monkeypatch.setattr(lifecycle, '_store', FirestoreLifecycleStore(store.client, namespace='test'))
    assert _saved_report('incident')
    result = save_outcome('incident', OutcomeRequest(outcome='not_fixed'))
    assert result['ticket_id']
    assert store.get('complaints', 'incident')['status'] == 'ticket_raised'


def test_unknown_backend_fails_closed(monkeypatch):
    monkeypatch.setattr(lifecycle, '_store', None)
    monkeypatch.setenv('PRODUCTLOOP_STATE_BACKEND', 'invalid')
    with pytest.raises(ValueError, match='must be sqlite or firestore'):
        lifecycle.get_store()


def test_default_backend_remains_local_sqlite(monkeypatch, tmp_path):
    monkeypatch.setattr(lifecycle, '_store', None)
    monkeypatch.delenv('PRODUCTLOOP_STATE_BACKEND', raising=False)
    monkeypatch.setenv('PRODUCTLOOP_STATE_DB', str(tmp_path / 'local.sqlite3'))
    local = lifecycle.get_store()
    try:
        assert type(local) is lifecycle.LifecycleStore
        assert local.draft('user', 'local')['report_id'] == 'local'
    finally:
        local.db.close()


def test_firestore_selection_does_not_fallback_to_sqlite(monkeypatch):
    from app.services import firestore_store
    monkeypatch.setattr(lifecycle, '_store', None)
    monkeypatch.setenv('PRODUCTLOOP_STATE_BACKEND', 'firestore')
    def unavailable():
        raise RuntimeError('Firestore unavailable')
    monkeypatch.setattr(firestore_store, 'FirestoreLifecycleStore', unavailable)
    with pytest.raises(RuntimeError, match='Firestore unavailable'):
        lifecycle.get_store()


@pytest.mark.parametrize('case', [
    'test_registration_reuse_and_unknown_details',
    'test_draft_confirm_and_event_idempotency',
    'test_outcomes_callback_and_restart_records',
    'test_report_details_scoped_to_owner_and_excludes_private_storage_payload',
])
def test_existing_http_lifecycle_contract_on_firestore(store, monkeypatch, case):
    from tests.unit import test_lifecycle
    monkeypatch.setattr(lifecycle, '_store', store)
    getattr(test_lifecycle, case)()


def test_service_appointment_contract_on_firestore(store, monkeypatch):
    from tests.unit.test_service_appointment import test_booking_is_durable_idempotent_and_does_not_resolve_report
    monkeypatch.setattr(lifecycle, '_store', store)
    test_booking_is_durable_idempotent_and_does_not_resolve_report()


def test_failed_bigquery_sync_retains_firestore_outbox(store, monkeypatch):
    from tests.unit.test_lifecycle import test_failed_sync_retains_queue_and_retry_acks
    monkeypatch.setattr(lifecycle, '_store', store)
    test_failed_sync_retains_queue_and_retry_acks(monkeypatch)
