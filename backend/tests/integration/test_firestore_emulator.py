"""Opt-in SDK integration: requires a separately running local emulator."""
import os
from uuid import uuid4

import pytest

@pytest.mark.skipif(not os.getenv('FIRESTORE_EMULATOR_HOST'), reason='Firestore emulator is not configured')
def test_real_sdk_atomic_persistence_and_restart():
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore
    from app.services.firestore_store import FirestoreLifecycleStore
    # Emulator-only, isolated namespace. Never use a production project/client.
    client = firestore.Client(project='productloop-emulator-test', credentials=AnonymousCredentials())
    namespace = 'test-' + uuid4().hex
    store = FirestoreLifecycleStore(client, namespace)
    try:
        record = store.draft('user', 'incident')
        reopened = FirestoreLifecycleStore(client, namespace)
        assert reopened.get('complaints', 'incident') == record
        assert len(reopened.pending()) == 2
        assert reopened.sync_status()['pending_writes'] == 2
        with pytest.raises(ValueError):
            with reopened.lock, reopened.db:
                reopened.draft('user', 'aborted')
                raise ValueError('rollback')
        assert reopened.get('complaints', 'aborted') is None
        reopened.ack(reopened.pending()[-1][0])
        assert reopened.pending() == []
    finally:
        for kind in ('complaints', 'registered_units', 'evidence', 'complaint_events', 'outbox', 'metadata'):
            for doc in store.root.collection(kind).stream():
                doc.reference.delete()
        client.close()
