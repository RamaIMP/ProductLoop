import test from 'node:test'
import assert from 'node:assert/strict'
import { formatSystemTime, watchSystemTime } from './systemClock.js'

test('formats local device hours and minutes, including midnight and noon', () => {
  assert.equal(formatSystemTime(new Date(2026, 9, 12, 0, 5)), '12:05')
  assert.equal(formatSystemTime(new Date(2026, 9, 12, 12, 0)), '12:00')
  assert.equal(formatSystemTime(new Date(2026, 9, 12, 15, 9)), '3:09')
})

test('rereads system time on ticks and cleans up its timer', () => {
  let current = new Date(2026, 9, 12, 9, 59), tick, cancelled
  const values = []
  const stop = watchSystemTime(value => values.push(value), {
    now: () => current,
    schedule: (fn, ms) => { assert.equal(ms, 1000); tick = fn; return 42 },
    cancel: id => { cancelled = id },
  })
  current = new Date(2026, 9, 12, 10, 0); tick()
  current = new Date(2026, 9, 12, 11, 30); tick()
  assert.deepEqual(values, ['9:59', '10:00', '11:30'])
  stop(); assert.equal(cancelled, 42)
})
