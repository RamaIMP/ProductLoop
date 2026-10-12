export const REFRESH_INTERVAL_MS = 5 * 60 * 1000

// One read at a time; changing scope disposes the old reader so stale responses
// cannot replace the new scope. This endpoint reads metrics, never invokes AI.
export function createOverviewRefresh({ url, onData, onError, onBusy,
  fetcher = fetch, schedule = setInterval, cancel = clearInterval }) {
  let disposed = false, busy = false, controller
  async function refresh() {
    if (disposed || busy) return
    busy = true
    controller = new AbortController()
    onBusy(true)
    try {
      const response = await fetcher(url, { signal: controller.signal })
      const data = await response.json()
      if (!response.ok) throw Error(data.detail || 'Unable to load signals')
      if (!disposed) { onData(data); onError('') }
    } catch (error) {
      if (!disposed && error.name !== 'AbortError') onError(error.message)
    } finally {
      busy = false
      if (!disposed) onBusy(false)
    }
  }
  const timer = schedule(refresh, REFRESH_INTERVAL_MS)
  return { refresh, dispose() { disposed = true; cancel(timer); controller?.abort() } }
}
