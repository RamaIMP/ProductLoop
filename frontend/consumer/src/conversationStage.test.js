import test from 'node:test'
import assert from 'node:assert/strict'
import { stageAfterResponse, quickReplies } from './conversationStage.js'

const guidance = { report: { report_id: 'PL-test', status: 'awaiting_feedback' },
  mode: 'gemini_reasoning', message: 'Clean the blade units.', sources: [{ chunk_id: 'clean' }],
  derived: { safety_flag: false } }

test('failed guidance does not display outcome buttons', () => {
  const stage = stageAfterResponse({ action: 'guidance_unavailable' })
  assert.equal(stage, 'guidance-unavailable')
  assert.deepEqual(quickReplies(stage, null, false, ''), [])
})

test('saved report waiting for guidance has no outcome buttons', () => {
  assert.deepEqual(quickReplies('awaiting-guidance', null, true, ''), [])
  assert.deepEqual(quickReplies('awaiting-guidance', null, false, 'Request failed'), [])
})
test('successful guidance unlocks buttons only after loading ends', () => {
  const stage = stageAfterResponse(guidance)
  assert.equal(stage, 'guidance')
  assert.deepEqual(quickReplies(stage, null, true, ''), [])
  assert.deepEqual(quickReplies(stage, null, false, ''), ['That fixed it', 'Still not fixed'])
})
test('later pending or failed request hides stale buttons', () => {
  assert.deepEqual(quickReplies('guidance', null, true, ''), [])
  assert.deepEqual(quickReplies('guidance', null, false, 'Network error'), [])
})
test('report alone, clarification and missing evidence are not guidance', () => {
  assert.equal(stageAfterResponse({ report: guidance.report }), 'initial')
  assert.equal(stageAfterResponse({ ...guidance, mode: 'gemini_conversation' }), 'initial')
  assert.equal(stageAfterResponse({ ...guidance, sources: [] }), 'initial')
})
test('safety, terminal states and ticket confirmation keep their own controls', () => {
  assert.equal(stageAfterResponse({ ...guidance, derived: { safety_flag: true } }), 'safety')
  assert.equal(stageAfterResponse({ ...guidance, report: { status: 'resolved' } }), 'done')
  assert.equal(stageAfterResponse({ ...guidance, action: 'ticket_confirm' }), 'ticket-confirm')
  assert.deepEqual(quickReplies('ticket-confirm', null, false, ''), ['Create ticket', 'Add more details'])
})
