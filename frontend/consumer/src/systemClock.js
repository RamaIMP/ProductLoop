// Deliberately use the browser/device timezone, not a fixed demo or server time.
export function formatSystemTime(date = new Date()) {
  return `${date.getHours() % 12 || 12}:${String(date.getMinutes()).padStart(2, '0')}`
}

export function watchSystemTime(update, { now = () => new Date(), schedule = setInterval, cancel = clearInterval } = {}) {
  const tick = () => update(formatSystemTime(now()))
  tick()
  const timer = schedule(tick, 1000)
  return () => cancel(timer)
}
