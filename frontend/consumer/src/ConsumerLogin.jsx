import { useEffect, useState } from 'react'
import './consumerLogin.css'

export default function ConsumerLogin({ configured, loading, busy, error, onLogin }) {
  const [time, setTime] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 60000)
    return () => clearInterval(timer)
  }, [])
  return <div className="stage-wrap consumer-login">
    <div>
      <div className="phone"><div className="screen">
        <div className="notch" aria-hidden="true" />
        <main className="page login-page">
          <div className="status white"><span aria-label="Current device time">{time.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</span><span aria-hidden="true">5G ▮▮▮</span></div>
          <header className="hero login-hero">
            <div className="brand"><span className="logo" aria-hidden="true">⟳</span> ProductLoop</div>
            <p>Welcome to ProductLoop</p>
            <h1>Your product.<br />Our support.</h1>
          </header>
          <div className="login-content">
            <section className="cta login-card" aria-label="Sign in">
              <div className="product-row"><div className="product-icon" aria-hidden="true">🪒</div><div><b>X500 Electric Shaver</b><small>Product support</small></div></div>
              <h2>Support starts here</h2>
              <p className="login-intro">Sign in to report a problem, track your reports and find service support.</p>
              {!configured ? <p className="login-notice" role="alert">Google sign-in is not configured yet. Please contact the app administrator.</p>
                : loading ? <p className="login-notice" role="status">Verifying your session…</p>
                  : <button className="google-login" disabled={busy} onClick={onLogin}><span className="google-letter" aria-hidden="true">G</span>{busy ? 'Signing in…' : 'Continue with Google'}</button>}
              {error && <p className="login-error" role="alert">{error}</p>}
              <p className="login-secure">Secure sign-in with Google</p>
            </section>
            <div className="login-benefits"><h2>Help, all in one place</h2><p>Describe your issue and attach images, videos or audio.</p><p>Keep track of your product reports.</p><p>Find nearby service centres.</p></div>
          </div>
          <footer className="login-footer">Your product support companion</footer>
        </main>
      </div></div>
      <p className="prototype-note">ProductLoop · X500 support</p>
    </div>
  </div>
}
