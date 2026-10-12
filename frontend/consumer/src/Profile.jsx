import { useEffect, useState } from 'react'
import { ReportNav } from './Reports'
import { profileDevice, profileFields } from './profileDetails'
import './profile.css'

export default function Profile({ api, userId, goHome, goReports, goServices, goProfile }) {
  const [units, setUnits] = useState(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    setUnits(null); setError('')
    api('/api/profile/registered-units?user_id=' + encodeURIComponent(userId))
      .then(result => { if (active) setUnits(result.units) })
      .catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [userId, attempt])
  const unit = units ? profileDevice(units) : null
  const count = units?.filter(item => (item.product_model || '').trim().toUpperCase() === 'X500').length || 0
  return <div className="page reports-page">
    <div className="reports-top"><h2>Profile</h2><small>Your account and product details</small></div>
    <div className="reports-scroll profile-content">
      <section className="report-card"><h3>Ramachandra</h3><small>Your account</small></section>
      {error ? <p role="alert">{error} <button onClick={() => setAttempt(value => value + 1)}>Retry</button></p> :
        units === null ? <p role="status">Loading product details…</p> :
        <section className="report-card">
          <div className="profile-product"><span aria-hidden="true">🪒</span><div><h3>X500 Electric Shaver</h3><small>{unit ? 'Registered' : 'Registration not linked'}</small></div></div>
          <dl>{profileFields(unit).map(([label, value]) => <div className="profile-field" key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
          {!unit && <p className="profile-note">{count > 1 ? 'More than one X500 record exists. A single registration has not been selected for this profile.' : 'No X500 registration is saved for this account yet. Missing details are not assumed.'}</p>}
        </section>}
    </div>
    <ReportNav active="profile" goHome={goHome} goReports={goReports} goServices={goServices} goProfile={goProfile} />
  </div>
}
