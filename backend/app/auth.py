"""Firebase identities and fail-closed API authorization.

Legacy user_id fields remain wire-compatible but must match the verified UID.
Staff are explicitly provisioned by UID in server configuration, never by email
suffix, request payload, or a browser-selected role.
"""
import os
import logging
import threading
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

_firebase_lock = threading.Lock()


def auth_mode():
    mode = os.getenv('PRODUCTLOOP_AUTH_MODE', 'firebase')
    if mode not in ('firebase', 'development'):
        raise RuntimeError('Invalid PRODUCTLOOP_AUTH_MODE')
    if mode == 'development' and os.getenv('K_SERVICE'):
        raise RuntimeError('Development authentication is forbidden on Cloud Run')
    if mode == 'firebase' and os.getenv('FIREBASE_AUTH_EMULATOR_HOST'):
        raise RuntimeError('Firebase authentication emulator is not permitted in secure mode')
    return mode


@lru_cache(maxsize=1)
def firebase_app():
    import firebase_admin
    from app import config
    project = os.getenv('FIREBASE_PROJECT_ID') or config.PROJECT_ID
    if not project:
        raise RuntimeError('Firebase project is not configured')
    with _firebase_lock:
        try:
            return firebase_admin.get_app('productloop-auth')
        except ValueError:
            return firebase_admin.initialize_app(options={'projectId': project}, name='productloop-auth')


def verify_token(token):
    from firebase_admin import auth
    # Also rejects disabled users and tokens revoked by an administrator.
    return auth.verify_id_token(token, app=firebase_app(), check_revoked=True)


async def identity(request: Request):
    if auth_mode() == 'development':
        if not request.client or request.client.host not in ('127.0.0.1', '::1', 'testclient'):
            raise HTTPException(403, 'Development authentication is loopback-only')
        return {'uid': 'demo-ramachandra', 'email': '', 'name': 'Local demo',
                'staff': True, 'development': True}
    value = request.headers.get('Authorization', '')
    scheme, _, token = value.partition(' ')
    if scheme.lower() != 'bearer' or not token or len(token) > 16384:
        raise HTTPException(401, 'Sign in with Google to continue', headers={'WWW-Authenticate': 'Bearer'})
    try:
        claims = await run_in_threadpool(verify_token, token)
    except Exception as exc:
        logging.getLogger(__name__).warning('Firebase token verification failed (%s)', type(exc).__name__)
        # Do not disclose tokens, account existence, or credential errors.
        raise HTTPException(401, 'Session could not be verified. Sign in again.',
                            headers={'WWW-Authenticate': 'Bearer'}) from None
    uid = claims.get('uid') or claims.get('sub')
    if not isinstance(uid, str) or not uid or claims.get('email_verified') is not True:
        raise HTTPException(401, 'A verified Google account is required')
    if claims.get('firebase', {}).get('sign_in_provider') != 'google.com':
        raise HTTPException(401, 'Sign in using Google')
    staff_uids = {s.strip() for s in os.getenv('PRODUCTLOOP_STAFF_UIDS', '').split(',') if s.strip()}
    return {'uid': uid, 'email': claims.get('email', ''), 'name': claims.get('name', ''),
            'staff': uid in staff_uids, 'development': False}


async def staff_access(user=Depends(identity)):
    if not user['staff']:
        raise HTTPException(403, 'Staff access is required')
    return user


async def consumer_access(request: Request, user=Depends(identity)):
    """Bind all legacy identity inputs to the token, including multipart uploads.

    Ownership is checked here for outcome/callback routes which historically
    accepted only a report ID. Handlers retain their existing owner checks too.
    """
    if user['development']:
        return user
    payload = {}
    if request.method in ('POST', 'PUT', 'PATCH'):
        content_type = request.headers.get('content-type', '').split(';')[0].strip().lower()
        if content_type == 'application/json':
            payload = await request.json()
            if not isinstance(payload, dict):
                raise HTTPException(422, 'Expected a JSON object')
        elif content_type in ('multipart/form-data', 'application/x-www-form-urlencoded'):
            payload = await request.form()
            if 'user_id' not in payload:
                raise HTTPException(403, 'Upload requires the signed-in user identity')
    supplied = request.query_params.getlist('user_id')
    if 'user_id' in payload:
        supplied.extend(payload.getlist('user_id') if hasattr(payload, 'getlist') else [payload['user_id']])
    if any(value != user['uid'] for value in supplied):
        raise HTTPException(403, 'Account identity does not match the signed-in user')
    from app.services.lifecycle import get_store
    ids = [request.path_params.get('report_id'), request.path_params.get('complaint_id'),
           payload.get('report_id'), payload.get('complaint_id')]
    for record_id in ids:
        if record_id is None or record_id == '':
            continue
        if not isinstance(record_id, str):
            raise HTTPException(422, 'Invalid report ID')
        record = await run_in_threadpool(get_store().get, 'complaints', record_id)
        if record and record['user_id'] != user['uid']:
            raise HTTPException(404, 'Report not found')
    return user
