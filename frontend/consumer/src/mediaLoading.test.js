import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { hasClearMediaFinding } from './mediaSummary.js'

// Exercise the actual upload handler with isolated dependencies: no cloud writes.
for (const unclear of [false, true]) test(unclear ? 'unclear upload waits for user without next-step loader or conversation call' : 'media findings switch loading wording before the text follow-up', async () => {
  const source = fs.readFileSync(new URL('./App.jsx', import.meta.url), 'utf8')
  const handler = source.slice(source.indexOf('  const attach ='), source.indexOf('  const confirm ='))
  let label, busy = false, calls = 0, release
  const pending = new Promise(resolve => { release = resolve })
  const data = { analysis_mode: 'multimodal_gemini', evidence_id: 'test-only',
    media_extraction: { symptoms: unclear ? ['unclear_description'] : ['hair_buildup'] }, extraction: { symptoms: ['hair_buildup'] }, derived: { safety_flag: false } }
  let conversationCalls = 0, stage
  let reachedFollowUp
  const reached = new Promise(resolve => { reachedFollowUp = resolve })
  const bindings = {
    runTurn: async (task, message) => { busy = true; label = message; try { await task() } finally { busy = false } },
    setBusyMessage: message => { assert.equal(unclear, false); label = message },
    setError: message => { throw Error(message) }, performance,
    URL: { createObjectURL: () => 'test-preview' }, setDraft: () => {},
    add: message => { if (message.evidenceId) assert.equal(label, unclear ? 'Analysing your media…' : 'Preparing next step…') },
    ensureIncident: async () => {}, FormData: class { append() {} },
    USER: 'isolated-test', incidentId: { current: 'isolated' }, crypto,
    draft: { message: '' }, text: '', extraction: null, debugEnabled: false, API: '',
    fetch: async () => {
      calls++
      assert.equal(label, 'Analysing your media…')
      return { ok: true, status: 200, json: async () => data }
    },
    recordDebug: () => {}, setUploads: () => {}, mediaSummary: () => 'Hair buildup detected.',
    hasClearMediaFinding, setFollowUp: () => {},
    bot: text => ({ from: 'bot', text }), setExtraction: () => {}, setDerived: () => {},
    setSafetyAdvice: () => {}, setStage: value => { stage = value }, messages: [],
    converse: async (_, payload) => {
      conversationCalls++
      assert.equal(payload.event, 'media_added')
      assert.equal(payload.extraction, data.extraction)
      reachedFollowUp()
      await pending
    },
  }
  const attach = new Function(...Object.keys(bindings), handler + '; return attach;')(...Object.values(bindings))
  const turn = attach('Photo', { size: 100, name: 'isolated.jpg', type: 'image/jpeg' })
  if (unclear) {
    await turn
    assert.equal(conversationCalls, 0)
    assert.equal(stage, 'initial')
    assert.equal(busy, false)
    return
  }
  await Promise.race([reached, turn.then(() => { throw Error('Follow-up was not reached') })])
  assert.equal(busy, true)
  assert.equal(label, 'Preparing next step…')
  assert.equal(calls, 1)
  release()
  await turn
  assert.equal(busy, false)
})
