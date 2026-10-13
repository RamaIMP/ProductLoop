// React is injected so both independent Vite apps use their own React instance.
export function createAuthGate(React, auth) {
  const { useEffect, useState } = React
  return function AuthGate({ children, staff = false, onSessionChange = () => {} }) {
    const [state, setState] = useState({ loading: true })
    const [error, setError] = useState('')
    const [busy, setBusy] = useState(false)
    const [retry, setRetry] = useState(0)
    useEffect(() => {
      if (!auth.configured) { setState({}); return }
      let version = 0
      const reset = auth.session.subscribe(() => { version++; onSessionChange(); setState({}) })
      const unsubscribe = auth.observe(async user => {
        auth.session.invalidate()
        const current = ++version
        setError('')
        if (!user) { setState({}); return }
        setState({ loading: true })
        try {
          const response = await auth.session.request('/api/auth/me')
          const profile = await response.json()
          if (!response.ok) throw Error(profile.detail || 'Could not verify your account')
          if (current === version) setState({ profile })
        } catch (err) { if (current === version) { setState({}); setError(err.message) } }
      })
      return () => { version++; unsubscribe(); reset(); onSessionChange() }
    }, [retry])
    async function login() {
      setBusy(true); setError('')
      try { await auth.login(); setRetry(n => n + 1) }
      catch (err) { setError(err.code === 'auth/popup-closed-by-user' ? 'Sign-in cancelled. You can try again.' : 'Google sign-in failed. Check the configured provider and authorized domain, then retry.') }
      finally { setBusy(false) }
    }
    async function logout() {
      auth.session.invalidate(); setState({}); setError('')
      try { await auth.logout() } catch { setError('Sign-out could not complete. Please retry.'); setRetry(n => n + 1) }
    }
    const profile = state.profile
    const style = { maxWidth: 540, margin: '8vh auto', padding: 28, fontFamily: 'system-ui', border: '1px solid #ccd5df', borderRadius: 16, background: '#fff', color: '#17243b' }
    if (!auth.configured) return <main style={style}><h1>ProductLoop {staff ? 'Staff' : 'Support'}</h1><p>Google sign-in is not configured yet. Add the Firebase web configuration and rebuild this app.</p></main>
    if (state.loading) return <main style={style} role="status">Verifying your session…</main>
    if (!profile) return <main style={style}><h1>ProductLoop {staff ? 'Staff' : 'Support'}</h1><p>{staff ? 'Sign in with your approved staff Google account.' : 'Sign in to manage your own product reports and service requests.'}</p><button disabled={busy} onClick={login}>{busy ? 'Signing in…' : 'Continue with Google'}</button>{error && <p role="alert">{error}</p>}</main>
    if (staff && !profile.staff) return <main style={style}><h1>Staff access required</h1><p>This account has not been approved for the staff dashboard. Ask your administrator to authorize your Firebase UID.</p><p>UID: <code>{profile.uid}</code></p><button onClick={() => setRetry(n => n + 1)}>Check access again</button> <button onClick={logout}>Sign out</button></main>
    return <React.Fragment key={profile.uid}><div style={{ padding: '10px 18px', background: '#eff4fb', color: '#17243b', display: 'flex', justifyContent: 'space-between', gap: 16, fontFamily: 'system-ui' }}><span>{profile.name || profile.email} · {staff ? 'Staff' : 'Consumer'}</span><button onClick={logout}>Sign out</button></div>{children(profile)}</React.Fragment>
  }
}
