import test from 'node:test'
import assert from 'node:assert/strict'
import { createSession } from './session.js'

const user = { uid: 'alice', getIdToken: async () => 'firebase-token' }
test('sends fresh bearer token and preserves multipart content type', async () => {
  let seen
  const session = createSession({ currentUser: () => user, signOut: async () => {}, apiBase: 'https://api.example',
    fetcher: async (url, options) => { seen = {url, ...options}; return new Response('{}') } })
  const form = new FormData(); form.set('user_id', 'alice')
  await session.request('/api/media/extract', { method: 'POST', body: form })
  assert.equal(seen.headers.get('Authorization'), 'Bearer firebase-token')
  assert.equal(seen.headers.get('Content-Type'), null)
  assert.equal(seen.credentials, 'omit')
  assert.equal(seen.redirect, 'error')
})
test('blocks token leakage and requests without a signed-in user', async () => {
  const session = createSession({ currentUser: () => null, signOut: async () => {}, apiBase: 'https://api.example', fetcher: () => assert.fail('must not fetch') })
  await assert.rejects(session.request('/api/reports'), /Sign in/)
  await assert.rejects(session.request('https://evil.example/api/reports'), /destination/)
})
test('401 clears the session instead of replaying a mutation', async () => {
  let signedOut = 0, cleared = 0, calls = 0
  const session = createSession({ currentUser: () => user, signOut: async () => signedOut++, apiBase: 'https://api.example',
    fetcher: async () => { calls++; return new Response('{}', {status:401}) } })
  session.subscribe(() => cleared++)
  await assert.rejects(session.request('/api/incidents', {method:'POST', body:'{}'}), /expired/)
  assert.equal(signedOut, 1); assert.equal(cleared, 1); assert.equal(calls, 1)
})
test('discards responses after sign-out or account switch', async () => {
  let finish
  const session = createSession({ currentUser: () => user, signOut: async () => {}, apiBase: 'https://api.example',
    fetcher: () => new Promise(resolve => {finish=resolve}) })
  const pending = session.request('/api/reports')
  await new Promise(resolve => setImmediate(resolve))
  session.invalidate(); finish(new Response('{}'))
  await assert.rejects(pending, /Account changed/)
})
