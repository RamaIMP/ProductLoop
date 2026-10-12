import { useEffect, useState } from 'react'
import { newestReports, reportStatus, reportTitle, reportResolution } from './reportPresentation'
import './reports.css'

export function ReportCard({ report, onOpen }) {
  return <button type="button" className="report incident-card" onClick={() => onOpen(report.report_id)}
    aria-label={`Open ${reportTitle(report)}, ${reportStatus(report)}, ${report.report_id}`}>
    <span className="report-icon" aria-hidden="true">{report.status === 'resolved' ? '✓' : report.status === 'ticket_raised' ? '🎫' : '📝'}</span>
    <div className="incident-copy"><b>{reportTitle(report)}</b>
      <small>{report.extraction?.product_model || report.product_model || 'Product'} · {report.serial_number || 'Device not linked'}</small>
      <small>#{report.report_id}</small>
      <small>{new Date(report.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}</small>
      {report.ticket_id && <small>Ticket: {report.ticket_id}</small>}
      <p>{reportResolution(report)}</p>
    </div>
    <span className={report.status === 'resolved' ? 'status-pill done' : 'status-pill'}>{reportStatus(report)}</span>
  </button>
}

export function ReportNav({ active, goHome, goReports, goServices, goProfile }) {
  return <nav aria-label="Main navigation">
    {[['home','🏠','Home',goHome],['reports','💬','Reports',goReports],['services','📍','Service',goServices]].map(([key,icon,label,action]) =>
      <button key={key} className={active === key ? 'active' : ''} aria-current={active === key ? 'page' : undefined} onClick={action}>{icon}<i>{label}</i></button>)}
    <button onClick={goProfile} className={active === 'profile' ? 'active' : ''} aria-current={active === 'profile' ? 'page' : undefined}>👤<i>Profile</i></button>
  </nav>
}

export function ReportsPage({ reports, loading, error, retry, openReport, goHome, goReports, goServices, goProfile }) {
  return <div className="page reports-page"><div className="reports-top"><h2>My reports</h2><small>All submitted incidents for your account</small></div>
    <div className="reports-scroll">
      {loading && <p role="status">Loading reports…</p>}
      {error && <p role="alert">{error} <button onClick={retry}>Retry</button></p>}
      {!loading && !error && !reports.length && <p>No reports yet. Submit an issue to see it here.</p>}
      {newestReports(reports).map(report => <ReportCard key={report.report_id} report={report} onOpen={openReport} />)}
    </div>
    <ReportNav active="reports" goHome={goHome} goReports={goReports} goServices={goServices} goProfile={goProfile} />
  </div>
}

export function ReportDetails({ reportId, userId, api, back, goHome }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    setData(null); setError('')
    api(`/api/reports/${encodeURIComponent(reportId)}?user_id=${encodeURIComponent(userId)}`)
      .then(result => { if (active) setData(result) })
      .catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [reportId, userId, attempt])
  const report = data?.report
  return <div className="page reports-page">
    <div className="reports-top"><button onClick={back}>‹ Back</button><HomeButton onClick={goHome} /><h2>Report details</h2></div>
    <div className="reports-scroll">
      {error ? <p role="alert">{error} <button onClick={() => setAttempt(value => value + 1)}>Retry</button></p> : !data ? <p role="status">Loading incident…</p> : <>
        <section className="report-card"><h3>{reportTitle(report)}</h3><p>{reportStatus(report)}</p><p>{reportResolution(report)}</p>
          <small>Report: {report.report_id}</small>
          {report.ticket_id && <p>Ticket: {report.ticket_id}</p>}
          <p>Product: {report.extraction?.product_model || report.product_model || 'Not recorded'}</p>
          <p>Serial: {report.serial_number || 'Device not linked'}</p>
          <p>Severity: {report.derived?.severity || 'Not recorded'} · Safety flag: {report.derived?.safety_flag == null ? 'Not recorded' : report.derived.safety_flag ? 'Yes' : 'No'}</p>
        </section>
        <section className="report-card"><h3>Evidence</h3>{data.evidence.length ? data.evidence.map(item =>
          <div key={item.evidence_id}><b>{item.original_filename || item.kind}</b><p>{item.extracted_summary?.replaceAll('_', ' ') || 'No extracted findings recorded.'}</p>
            <small>Storage: {item.storage_status || 'Unknown'} · Analysis: {item.extraction_status || 'Unknown'}</small></div>) : <p>No linked evidence records.</p>}</section>
        {report.service_appointment && <section className="report-card"><h3>Service appointment</h3>
          <p>{report.service_appointment.centre_name}</p>
          <p>{new Date(report.service_appointment.scheduled_start).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })} IST</p>
          <p>Reference: {report.service_appointment.booking_id?.replace(/^DEMO-/, '')}</p>
          <small>Appointment booked</small>
        </section>}
        <section className="report-card"><h3>Recorded history</h3>
          <p>This is the saved incident activity, not a full chat transcript. Older reports may have limited history.</p>
          {data.events.length ? <ol>{data.events.map(event => <li key={event.event_id}>
            <b>{event.event_type.replaceAll('_', ' ')}</b><small>{new Date(event.occurred_at).toLocaleString()}</small>
            {event.new_status && <p>{event.new_status.replaceAll('_', ' ')}</p>}
          </li>)}</ol> : <p>No activity history recorded.</p>}
        </section>
      </>}
    </div>
  </div>
}
import HomeButton from './HomeButton.jsx'
