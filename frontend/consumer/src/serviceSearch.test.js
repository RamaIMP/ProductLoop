import test from 'node:test'
import assert from 'node:assert/strict'
import { serviceSearchUrl, coordinatesForSearch } from './serviceSearch.js'

test('no location uses nearby Google Maps search, not fixed cities', () => {
  const url = new URL(serviceSearchUrl())
  assert.equal(url.origin, 'https://www.google.com')
  assert.equal(url.searchParams.get('api'), '1')
  assert.equal(url.searchParams.get('query'), 'electric shaver service centre near me')
})
test('manual location and optional brand are correctly encoded', () => {
  const query = new URL(serviceSearchUrl('Kochi & 682001', 'Philips')).searchParams.get('query')
  assert.equal(query, 'Philips electric shaver service centre near Kochi & 682001')
})
test('browser location anchors the service search', () => {
  const location = coordinatesForSearch(10.123456, 76.987654)
  assert.equal(location, '10.1235,76.9877')
  assert.ok(new URL(serviceSearchUrl(location)).searchParams.get('query').endsWith(`near ${location}`))
})
test('invalid coordinates are rejected', () => {
  for (const coords of [[NaN, 2], [91, 0], [0, 181]]) assert.throws(() => coordinatesForSearch(...coords))
})
