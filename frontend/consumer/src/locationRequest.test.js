import test from 'node:test'
import assert from 'node:assert/strict'
import { requestLocation, locationErrorMessage } from './locationRequest.js'

test('successful geolocation returns coordinates', async () => {
  const position = { coords: { latitude: 12, longitude: 77 } }
  assert.equal(await requestLocation({ getCurrentPosition: success => success(position) }), position)
})
test('permission denial offers browser settings and manual fallback', async () => {
  await assert.rejects(requestLocation({ getCurrentPosition: (_, failure) => failure({ code: 1 }) }), error => error.code === 1)
  assert.match(locationErrorMessage({ code: 1 }), /permission is blocked/)
})
test('silent browser or unanswered prompt times out', async () => {
  await assert.rejects(requestLocation({ getCurrentPosition() {} }, 5), error => error.code === 3)
  assert.match(locationErrorMessage({ code: 3 }), /timed out/)
})
test('unsupported location and synchronous failure reject safely', async () => {
  await assert.rejects(requestLocation(undefined), /unavailable/)
  await assert.rejects(requestLocation({ getCurrentPosition() { throw new Error('blocked') } }), /blocked/)
  assert.match(locationErrorMessage({ code: 2 }), /city\/postcode/)
})
