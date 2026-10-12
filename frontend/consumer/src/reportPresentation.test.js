import test from 'node:test'
import assert from 'node:assert/strict'
import { newestReports, reportStatus, reportTitle, reportResolution } from './reportPresentation.js'

test('home shows latest three while reports page shows all without mutating input', () => {
  const reports = [1, 4, 2, 5, 3].map(day => ({ report_id: String(day), created_at: `2026-10-0${day}T00:00:00Z` }))
  assert.deepEqual(newestReports(reports, 3).map(item => item.report_id), ['5','4','3'])
  assert.equal(newestReports(reports).length, 5)
  assert.deepEqual(reports.map(item => item.report_id), ['1','4','2','5','3'])
})
test('unresolved has its own label; ticket ID is excluded from badge', () => {
  assert.equal(reportStatus({ status: 'unresolved' }), 'Unresolved')
  assert.equal(reportStatus({ status: 'ticket_raised', ticket_id: 'SR-LONG-ID' }), 'Ticket raised')
})
test('resolution does not invent a successful remedy', () => {
  assert.equal(reportResolution({ status: 'resolved' }), 'You confirmed the issue was resolved.')
  assert.doesNotMatch(reportResolution({ status: 'resolved' }), /cleaning/)
})
test('callback uses recorded timestamp instead of stale Today label', () => {
  const result = reportResolution({ status: 'ticket_raised', callback: {
    slot: 'Today · 2:00 PM', scheduled_start: '2026-10-10T14:00:00+05:30', time_zone: 'Asia/Kolkata',
  } })
  assert.match(result, /10 Oct 2026/)
  assert.doesNotMatch(result, /Today/)
  assert.doesNotMatch(result, /demo|no real call/i)
})
test('title handles missing legacy classification and symptom details', () => {
  assert.equal(reportTitle({}), 'Reported issue')
  assert.equal(reportTitle({ extraction: { symptoms: ['hair_buildup'] } }), 'hair buildup')
})
