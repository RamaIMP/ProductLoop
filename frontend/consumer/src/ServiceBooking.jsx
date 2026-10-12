import { useEffect, useState } from 'react'

const dateLabel = value => new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' })

export default function ServiceBooking({ centre, api, userId, reportId, back, done }) {
  const [reports, setReports] = useState([])
  const [selectedReport, setSelectedReport] = useState(reportId || '')
  const [slots, setSlots] = useState([])
  const [slot, setSlot] = useState('')
  const [booking, setBooking] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    Promise.all([api('/api/reports?user_id=' + encodeURIComponent(userId)), api('/api/callback-slots')])
      .then(([items, times]) => {
        if (!active) return
        const eligible = items.filter(r => r.status !== 'resolved')
        setReports(eligible); setSlots(times); setSlot('')
        // Never silently switch an explicitly linked complaint to another report.
        setSelectedReport(reportId
          ? (eligible.some(r => r.report_id === reportId) ? reportId : '')
          : eligible.length === 1 ? eligible[0].report_id : '')
      }).catch(err => { if (active) setError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [api, userId, reportId, attempt])
  const selected = reports.find(r => r.report_id === selectedReport)
  const saved = booking || selected?.service_appointment
  const submit = async event => {
    event.preventDefault()
    if (saving || !slot || !selectedReport) return
    setSaving(true); setError('')
    try {
      setBooking(await api('/api/reports/' + encodeURIComponent(selectedReport) + '/service-appointment', {
        method: 'POST', body: JSON.stringify({ user_id: userId, centre_id: centre.id, scheduled_start: slot }),
      }))
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }
  if (saved) return <section className="services service-booking" aria-live="polite">
    <div className="booking-success">✓ Appointment booked</div>
    <h3>{saved.centre_name}</h3>
    <dl className="booking-details">
      <div><dt>Booking reference</dt><dd>{saved.booking_id?.replace(/^DEMO-/, '')}</dd></div>
      <div><dt>Appointment (India time)</dt><dd>{dateLabel(saved.scheduled_start)} · 30 minutes · IST</dd></div>
      <div><dt>Device</dt><dd>{saved.product_model} · {saved.serial_number || 'Serial not linked'}</dd></div>
      <div><dt>Complaint</dt><dd>{saved.complaint_id}</dd></div>
    </dl>
    <p>Your report remains unresolved until you confirm the issue is fixed.</p>
    <button type="button" onClick={done}>Done</button>
  </section>
  return <section className="services service-booking">
    <button type="button" disabled={saving} onClick={back}>‹ Back to centres</button>
    <h3>Book a service appointment</h3><p>{centre.name}</p>
    {loading ? <p role="status">Loading reports and appointment slots…</p> : <>
      {error && <p role="alert">{error} <button type="button" disabled={saving} onClick={() => setAttempt(n => n + 1)}>Reload available slots</button></p>}
      {!selectedReport ? <p>{reportId
        ? 'This report is not available for service booking. Open your unresolved report and try again.'
        : reports.length > 1
          ? 'Open the issue you need help with from My reports to book service for it.'
          : 'Submit an unresolved problem report first, then return here to book service.'}</p> :
        <form onSubmit={submit}>
          <fieldset disabled={saving}><legend>Choose date and time (IST)</legend>
            {slots.map(s => <label className="appointment-slot" key={s.scheduled_start}><input type="radio" name="appointment-slot" value={s.scheduled_start} checked={slot === s.scheduled_start} onChange={e => setSlot(e.target.value)} required />{dateLabel(s.scheduled_start)} · 30 minutes</label>)}
          </fieldset>
          <button className="booking-confirm" type="submit" disabled={saving || !slot || !selectedReport}>{saving ? 'Saving appointment…' : 'Confirm appointment'}</button>
        </form>}
    </>}
  </section>
}
