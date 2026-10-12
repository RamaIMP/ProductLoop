import test from 'node:test'
import assert from 'node:assert/strict'
import { profileDevice, profileDate, profileFields } from './profileDetails.js'

test('only the unique X500 registration is used', () => {
  const x500 = { product_model: 'X500', serial_number: 'saved-serial' }
  assert.equal(profileDevice([x500, { product_model: 'X700' }]), x500)
  assert.equal(profileDevice([]), null)
  assert.equal(profileDevice([x500, { ...x500, serial_number: 'other' }]), null)
})
test('saved dates and serial appear in profile', () => {
  const fields = Object.fromEntries(profileFields({ serial_number: 'ABC', purchase_date: '2026-08-12', registered_at: '2026-10-09T12:00:00Z' }))
  assert.equal(fields['Serial number'], 'ABC')
  assert.equal(fields['Purchase date'], '12 Aug 2026')
  assert.equal(fields['Registration date'], '9 Oct 2026')
})
test('unknown details and warranty are never fabricated', () => {
  const fields = Object.fromEntries(profileFields(null))
  assert.equal(fields['Purchase date'], 'Not recorded')
  assert.equal(fields['Registration date'], 'Not recorded')
  assert.equal(fields['Warranty status'], 'Not verified')
  assert.equal(profileDate('invalid'), 'Not recorded')
})
test('batch, region and warranty come from the registration', () => {
  const fields = Object.fromEntries(profileFields({ batch_id: 'DEMO-BATCH-001', region: 'India', warranty_status: 'Active (demo)' }))
  assert.equal(fields['Batch'], 'DEMO-BATCH-001')
  assert.equal(fields['Registration region'], 'India')
  assert.equal(fields['Warranty status'], 'Active (demo)')
})
