import pytest
import re
from fastapi.testclient import TestClient
from app.main import app
from app import auth
from app.services.lifecycle import get_store


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setenv('PRODUCTLOOP_AUTH_MODE', 'firebase')
    monkeypatch.delenv('PRODUCTLOOP_STAFF_UIDS', raising=False)
    monkeypatch.delenv('PRODUCTLOOP_DEMO_STAFF_ACCESS', raising=False)
    claims = {'uid': 'alice', 'sub': 'alice', 'email_verified': True,
              'email': 'alice@example.com', 'firebase': {'sign_in_provider': 'google.com'}}
    monkeypatch.setattr(auth, 'verify_token', lambda token: claims if token == 'valid' else (_ for _ in ()).throw(ValueError('invalid')))
    return TestClient(app, headers={'Authorization': 'Bearer valid'}), claims


@pytest.mark.parametrize('path', ['/api/reports?user_id=alice', '/api/dashboard/overview',
    '/api/manufacturing/analysis', '/api/persistence/status', '/api/auth/me', '/api/callback-slots'])
def test_api_requires_verified_session(signed_in, path):
    assert TestClient(app).get(path).status_code == 401
    assert TestClient(app, headers={'Authorization': 'Bearer forged'}).get(path).status_code == 401


def test_health_public_docs_disabled(signed_in):
    c = TestClient(app)
    assert c.get('/health').status_code == 200
    assert c.get('/docs').status_code == 404
    assert c.get('/openapi.json').status_code == 404


def test_verified_profile_and_staff_allowlist(signed_in, monkeypatch):
    c, claims = signed_in
    claims['staff'] = True  # Client/custom claims do not provision staff here.
    assert c.get('/api/auth/me').json()['staff'] is False
    assert c.get('/api/persistence/status').status_code == 403
    monkeypatch.setenv('PRODUCTLOOP_STAFF_UIDS', ' alice, bob ')
    assert c.get('/api/auth/me').json()['staff'] is True
    assert c.get('/api/persistence/status').status_code == 200
    monkeypatch.setenv('PRODUCTLOOP_STAFF_UIDS', 'bob')
    assert c.get('/api/persistence/status').status_code == 403


@pytest.mark.parametrize('path', ['/api/dashboard/overview', '/api/dashboard/signals',
    '/api/dashboard/complaints/x', '/api/dashboard/complaints/x/evidence/e/media',
    '/api/manufacturing/analysis', '/api/manufacturing/evidence'])
def test_consumer_cannot_access_staff_routes(signed_in, path):
    c, _ = signed_in
    assert c.get(path).status_code == 403


def test_demo_staff_access_requires_verified_google_session(signed_in, monkeypatch):
    c, claims = signed_in
    monkeypatch.setenv('PRODUCTLOOP_DEMO_STAFF_ACCESS', '1')
    assert c.get('/api/auth/me').json()['staff'] is True
    assert c.get('/api/auth/me').json()['demo_staff_access'] is True
    assert c.get('/api/persistence/status').status_code == 200
    claims['uid'] = claims['sub'] = 'another-google-user'
    assert c.get('/api/persistence/status').status_code == 200
    assert TestClient(app).get('/api/persistence/status').status_code == 401
    assert c.get('/api/persistence/status', headers={'Authorization': 'Bearer forged'}).status_code == 401
    claims['email_verified'] = False
    assert c.get('/api/persistence/status').status_code == 401
    claims['email_verified'] = True
    claims['firebase']['sign_in_provider'] = 'password'
    assert c.get('/api/persistence/status').status_code == 401


@pytest.mark.parametrize('value', ['0', 'false', 'true', ''])
def test_demo_staff_flag_requires_explicit_one(signed_in, monkeypatch, value):
    c, _ = signed_in
    monkeypatch.setenv('PRODUCTLOOP_DEMO_STAFF_ACCESS', value)
    assert c.get('/api/persistence/status').status_code == 403


def test_demo_staff_can_be_disabled(signed_in, monkeypatch):
    c, _ = signed_in
    monkeypatch.setenv('PRODUCTLOOP_DEMO_STAFF_ACCESS', '1')
    assert c.get('/api/persistence/status').status_code == 200
    monkeypatch.setenv('PRODUCTLOOP_DEMO_STAFF_ACCESS', '0')
    assert c.get('/api/persistence/status').status_code == 403


def test_identity_spoofing_rejected(signed_in):
    c, _ = signed_in
    assert c.get('/api/reports?user_id=bob').status_code == 403
    assert c.get('/api/reports?user_id=alice&user_id=bob').status_code == 403
    assert c.post('/api/incidents', json={'user_id': 'bob', 'complaint_id': 'PL-' + 'a'*32}).status_code == 403
    assert c.post('/api/media/extract', data={'user_id': 'bob'}, files={'file': ('a.jpg', b'image', 'image/jpeg')}).status_code == 403
    assert c.post('/api/media/extract', files={'file': ('a.jpg', b'image', 'image/jpeg')}).status_code == 403
    assert get_store().all('complaints') == []


def test_cross_account_ids_blocked_even_without_user_field(signed_in):
    c, _ = signed_in
    cid = 'PL-' + 'b'*32
    store = get_store()
    report = store.draft('bob', cid)
    report = store.save_report({**report, 'submitted_at': report['created_at']}, 'report_submitted')
    assert c.get(f'/api/reports/{cid}?user_id=alice').status_code == 404
    assert c.post(f'/api/reports/{cid}/outcome', json={'outcome': 'helped'}).status_code == 404
    assert c.post(f'/api/reports/{cid}/callback', json={'slot': 'Tomorrow'}).status_code == 404
    assert c.post('/api/conversation', json={'user_id': 'alice', 'report_id': cid, 'message': 'Hello'}).status_code == 404
    assert store.get('complaints', cid) == report


def test_owner_can_create_and_read_only_own_records(signed_in):
    c, _ = signed_in
    cid = 'PL-' + 'a'*32
    payload = {'user_id': 'alice', 'complaint_id': cid}
    assert c.post('/api/incidents', json=payload).status_code == 200
    result = c.post('/api/reports/confirm', json={**payload, 'consent_share': False,
        'extraction': {'symptoms': ['pulling_hair'], 'confidence': 1}})
    assert result.status_code == 201
    assert result.json()['report']['user_id'] == 'alice'
    get_store().draft('bob', 'PL-' + 'b'*32)
    r = c.get('/api/reports?user_id=alice')
    assert [r['report_id'] for r in r.json()] == [cid]
    assert r.headers['cache-control'] == 'private, no-store'
    assert c.post(f'/api/reports/{cid}/outcome', json={'outcome': 'helped'}).status_code == 200


def test_invalid_provider_or_unverified_email_rejected(signed_in):
    c, claims = signed_in
    claims['email_verified'] = False
    assert c.get('/api/auth/me').status_code == 401
    claims['email_verified'] = True
    claims['firebase']['sign_in_provider'] = 'password'
    assert c.get('/api/auth/me').status_code == 401


def test_development_cannot_run_on_cloud_run(monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'staging')
    with pytest.raises(RuntimeError, match='forbidden'):
        auth.auth_mode()


def test_default_is_secure(monkeypatch):
    monkeypatch.delenv('PRODUCTLOOP_AUTH_MODE')
    assert auth.auth_mode() == 'firebase'
    assert TestClient(app).get('/api/auth/me').status_code == 401


def test_firebase_verifier_uses_revocation_check(monkeypatch):
    from firebase_admin import auth as firebase_auth
    marker = object()
    monkeypatch.setattr(auth, 'firebase_app', lambda: marker)
    seen = {}
    def verify(token, **kwargs):
        seen.update(token=token, **kwargs)
        return {'uid': 'alice'}
    monkeypatch.setattr(firebase_auth, 'verify_id_token', verify)
    assert auth.verify_token('signed-token')['uid'] == 'alice'
    assert seen == {'token': 'signed-token', 'app': marker, 'check_revoked': True}


def test_every_mounted_api_route_rejects_anonymous_requests(signed_in):
    client = TestClient(app)
    for route in app.routes:
        if not getattr(route, 'path', '').startswith('/api/'):
            continue
        path = re.sub(r'\{[^}]+\}', 'unowned', route.path)
        for method in route.methods - {'OPTIONS', 'HEAD'}:
            response = client.request(method, path)
            assert response.status_code == 401, (method, path, response.text)


def test_staff_can_reach_review_routes_from_nonlocal_client(signed_in, monkeypatch):
    from app.api import dashboard
    monkeypatch.setenv('PRODUCTLOOP_STAFF_UIDS', 'alice')
    monkeypatch.setattr(dashboard, 'complaint_detail', lambda cid: {'complaint': {'complaint_id': cid}})
    client = TestClient(app, client=('192.0.2.1', 1000), headers={'Authorization': 'Bearer valid'})
    assert client.get('/api/dashboard/complaints/authorized').status_code == 200


def test_secure_mode_rejects_auth_emulator(monkeypatch):
    monkeypatch.setenv('PRODUCTLOOP_AUTH_MODE', 'firebase')
    monkeypatch.setenv('FIREBASE_AUTH_EMULATOR_HOST', 'localhost:9099')
    with pytest.raises(RuntimeError, match='emulator'):
        auth.auth_mode()
