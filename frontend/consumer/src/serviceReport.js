// Booking needs a submitted report, including when safety bypasses troubleshooting.
export async function prepareServiceReport({ report, ensureIncident, api, userId, extraction, derived, consentShare = false }) {
  if (report?.report_id) return report
  if (!extraction) throw new Error('Please describe the issue before booking service.')
  const complaintId = await ensureIncident()
  const result = await api('/api/reports/confirm', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, complaint_id: complaintId,
      extraction, derived, consent_share: consentShare }),
  })
  if (result.report?.report_id !== complaintId) throw new Error('Could not link your report. Please try again.')
  return result.report
}
