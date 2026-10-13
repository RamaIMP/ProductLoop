// SDK-independent transport: never put tokens in URLs or application storage.
export function createSession({ currentUser, signOut, fetcher = fetch, apiBase }) {
  const base = new URL(apiBase)
  if (base.protocol !== 'https:' && !['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)) {
    throw Error('The API must use HTTPS')
  }
  const listeners = new Set()
  let generation = 0
  function invalidate() { generation++; for (const callback of listeners) callback() }
  async function request(path, options = {}) {
    const url = new URL(path, base)
    if (url.origin !== base.origin || !url.pathname.startsWith('/api/')) throw Error('Invalid API destination')
    const user = currentUser()
    if (!user) throw Error('Sign in to continue')
    const started = generation
    const headers = new Headers(options.headers)
    headers.set('Authorization', 'Bearer ' + await user.getIdToken())
    if (started !== generation || currentUser()?.uid !== user.uid) throw Error('Account changed; request cancelled')
    if (typeof options.body === 'string' && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    const response = await fetcher(url.toString(), { ...options, headers, credentials: 'omit', cache: 'no-store', redirect: 'error' })
    if (started !== generation || currentUser()?.uid !== user.uid) throw Error('Account changed; response discarded')
    if (response.status === 401) {
      invalidate()
      await signOut()
      throw Error('Your session expired. Please sign in again.')
    }
    return response
  }
  return { request, invalidate, subscribe(callback) { listeners.add(callback); return () => listeners.delete(callback) } }
}
