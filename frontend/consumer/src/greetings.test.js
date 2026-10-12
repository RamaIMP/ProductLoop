import test from 'node:test'
import assert from 'node:assert/strict'
import cases from '../../../shared/greeting-cases.json' with { type: 'json' }
import { greetingReply } from './greetings.js'

for (const message of cases.greetings) {
  test(`instant greeting: ${message}`, () => assert.ok(greetingReply(message)))
}
for (const message of cases.not_greetings) {
  test(`not a standalone greeting: ${message}`, () => assert.equal(greetingReply(message), null))
}
test('time-of-day response', () => assert.match(greetingReply('Good morning!'), /^Good morning!/))
