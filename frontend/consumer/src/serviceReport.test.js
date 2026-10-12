import test from 'node:test'
import assert from 'node:assert/strict'
import { prepareServiceReport } from './serviceReport.js'

test('safety draft is submitted with the same complaint ID, without implicit sharing or LLM calls', async () => {
  const calls = []
  const report = await prepareServiceReport({ userId: 'user', extraction: { symptoms: ['burning_smell'] },
    derived: { safety_flag: true }, ensureIncident: async () => 'PL-safety',
    api: async (path, options) => { calls.push([path, JSON.parse(options.body)]); return { report: { report_id: 'PL-safety' } } } })
  assert.equal(report.report_id, 'PL-safety')
  assert.equal(calls.length, 1)
  assert.equal(calls[0][0], '/api/reports/confirm')
  assert.equal(calls[0][1].complaint_id, 'PL-safety')
  assert.equal(calls[0][1].consent_share, false)
  assert.equal(calls[0][1].derived.safety_flag, true)
})
test('existing report is reused without another submission', async () => {
  const report = { report_id: 'PL-existing', consent_share: true }
  assert.equal(await prepareServiceReport({ report }), report)
})
test('explicit sharing choice is passed to confirmation', async () => {
  await prepareServiceReport({ extraction: {}, consentShare: true, ensureIncident: async () => 'PL-new',
    api: async (_, options) => { assert.equal(JSON.parse(options.body).consent_share, true); return { report: { report_id: 'PL-new' } } } })
})
test('failed or mismatched saves cannot proceed with an unrelated report', async () => {
  const args = { extraction: {}, ensureIncident: async () => 'PL-current' }
  await assert.rejects(prepareServiceReport({ ...args, api: async () => { throw new Error('Offline') } }), /Offline/)
  await assert.rejects(prepareServiceReport({ ...args, api: async () => ({ report: { report_id: 'PL-other' } }) }), /Could not link/)
  await assert.rejects(prepareServiceReport({}), /describe the issue/)
})
