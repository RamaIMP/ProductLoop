export function newestReports(reports, limit) {
  const sorted = [...reports].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  return limit == null ? sorted : sorted.slice(0, limit)
}
export function reportStatus(report) {
  return ({ resolved: 'Resolved', unresolved: 'Unresolved', ticket_raised: 'Ticket raised',
    awaiting_feedback: 'Awaiting feedback' })[report.status] || 'Status unavailable'
}
export function reportTitle(report) {
  const symptoms = (report.extraction?.symptoms || []).filter(item => item !== 'unclear_description')
  return (symptoms.length ? symptoms.join(', ') : report.derived?.issue_type || 'Reported issue').replaceAll('_', ' ')
}
export function reportResolution(report) {
  if (report.status === 'resolved') return 'You confirmed the issue was resolved.'
  if (report.callback) {
    const callback = report.callback
    const time = callback.scheduled_start
      ? new Date(callback.scheduled_start).toLocaleString('en-IN', { timeZone: callback.time_zone || 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' })
      : callback.slot || 'time not recorded'
    return `Callback requested: ${time}.`
  }
  if (report.status === 'ticket_raised') return 'Support ticket created. Resolution pending.'
  if (report.status === 'unresolved') return 'You reported that the issue is still not fixed.'
  return 'Waiting for your feedback on the guidance.'
}

