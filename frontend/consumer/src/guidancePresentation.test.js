import test from 'node:test'
import assert from 'node:assert/strict'
import { guidancePresentation } from './guidancePresentation.js'

const reply = { mode: 'gemini_reasoning', message: 'Clean the blade units.', sources: [{ chunk_id: 'cleaning' }], derived: { safety_flag: false } }
test('sourced remedy appears in the green first-remedy card', () => {
  assert.equal(guidancePresentation(reply).title, 'Try this first')
})
test('already tried cleaning uses next steps title', () => {
  assert.equal(guidancePresentation({ ...reply, extraction: { context: { persists_after_cleaning: 'yes' } } }).title, 'Next steps')
})
test('safety warnings do not become remedies', () => {
  assert.equal(guidancePresentation({ ...reply, derived: { safety_flag: true } }), null)
  assert.equal(guidancePresentation({ ...reply, action: 'stop_use' }), null)
})
test('missing knowledge and normal chat retain normal bubbles', () => {
  assert.equal(guidancePresentation({ ...reply, sources: [] }), null)
  assert.equal(guidancePresentation({ ...reply, mode: 'workflow' }), null)
})
