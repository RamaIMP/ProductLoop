import { useEffect, useRef, useState } from 'react'
import { requestLocation, locationErrorMessage } from './locationRequest'
import { demoServiceCentres } from './demoServiceCentres'
import './services.css'
import ServiceBooking from './ServiceBooking'

export default function Services({ api, userId, reportId, done }) {
  const [centre, setCentre] = useState(null)
  const [location, setLocation] = useState('')
  const [resultsFor, setResultsFor] = useState(null)
  const [locating, setLocating] = useState(false)
  const [error, setError] = useState('')
  const active = useRef(true)
  const heading = useRef(null)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  useEffect(() => { if (resultsFor) heading.current?.focus() }, [resultsFor])
  const locate = async () => {
    setError(''); setLocating(true)
    try {
      await requestLocation(navigator.geolocation)
      if (active.current) setResultsFor('your current location')
    } catch (error) {
      if (active.current) setError(locationErrorMessage(error))
    } finally {
      if (active.current) setLocating(false)
    }
  }
  const search = event => {
    event.preventDefault()
    if (!location.trim()) { setError('Enter your city or postcode to continue.'); return }
    setError(''); setResultsFor(location.trim())
  }
  if (centre) return <ServiceBooking centre={centre} api={api} userId={userId} reportId={reportId} back={() => setCentre(null)} done={done} />
  if (resultsFor) return <section className="services service-results">
    <button type="button" onClick={() => { setResultsFor(null); setError('') }}>‹ Change location</button>
    <h3 ref={heading} tabIndex={-1}>Service centre results</h3>
    <p>Search area: {resultsFor}</p>
    <div className="service-centre-list">{demoServiceCentres.map(centre => <article className="service-centre-card" key={centre.id}>
      <div className="service-centre-heading"><h4>{centre.name}</h4><span>{centre.distanceKm.toFixed(1)} km</span></div>
      <p>{centre.address}</p><p>X500 electric-shaver support</p>
      <dl><div><dt>Phone</dt><dd>{centre.phone}</dd></div><div><dt>Email</dt><dd>{centre.email}</dd></div></dl>
      <button type="button" className="booking-confirm" onClick={() => setCentre(centre)}>Book service appointment →</button>
    </article>)}</div>
  </section>
  return <section className="services">
    <h3>Find a service centre</h3><p>Choose your location to find service centres.</p>
    <button type="button" onClick={locate} disabled={locating}>{locating ? 'Finding your location…' : '📍 Use my current location'}</button>
    {locating && <p role="status">Allow location access in your browser. This may take up to 10 seconds.</p>}
    {error && <p role="alert">{error}</p>}
    <form onSubmit={search}>
      <label className="service-location-label" htmlFor="service-location">City / postcode / location</label>
      <input id="service-location" className="service-location-input" value={location} onChange={e => { setLocation(e.target.value); setError('') }} maxLength={160} placeholder="Enter your city or postcode" disabled={locating} />
      <button type="submit" disabled={locating}>Show service centres →</button>
    </form>
    <small>Location is used only for this screen, not sent to Gemini or saved in your report.</small>
  </section>
}
