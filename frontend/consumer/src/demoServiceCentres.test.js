import test from 'node:test'
import assert from 'node:assert/strict'
import { demoServiceCentres } from './demoServiceCentres.js'

test('demo results provide three unique centres ordered by sample distance', () => {
  assert.equal(demoServiceCentres.length, 3)
  assert.equal(new Set(demoServiceCentres.map(c => c.id)).size, 3)
  assert.deepEqual(demoServiceCentres.map(c => c.distanceKm), [1.2, 2.8, 4.5])
})
test('all dummy centres have clearly fictional contact details', () => {
  for (const centre of demoServiceCentres) {
    assert.doesNotMatch(centre.name, /Demo/)
    assert.match(centre.phone, /00000/)
    assert.match(centre.email, /@xshaver\.example$/)
    assert.ok(centre.address)
  }
})
