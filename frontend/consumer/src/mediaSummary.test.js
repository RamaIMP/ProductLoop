import test from 'node:test'
import assert from 'node:assert/strict'
import { mediaSummary, mediaStorageNotice } from './mediaSummary.js'

test('storage disclosure reflects actual save status', () => {
  assert.match(mediaStorageNotice('pending'), /We’re saving this file/)
  assert.match(mediaStorageNotice('uploaded'), /has been saved/)
  assert.match(mediaStorageNotice('failed'), /could not be saved/)
  assert.match(mediaStorageNotice('unknown'), /couldn’t confirm/)
})

test('explains detected symptom in readable language', () => {
  assert.equal(mediaSummary({ symptoms: ['rattling_sound'], confidence: 0.9 }),
    'Based on this file, the analysis suggests rattling sound.')
})
test('does not invent a diagnosis for unclear media', () => {
  assert.match(mediaSummary({ symptoms: ['unclear_description'], confidence: 0.3 }), /couldn’t identify a clear issue/)
})
test('low confidence is explicitly qualified', () => {
  assert.match(mediaSummary({ symptoms: ['visible_damage'], confidence: 0.5 }), /uncertain/)
})
test('multiple findings appear without internal enum formatting', () => {
  assert.match(mediaSummary({ symptoms: ['hair_buildup', 'visible_damage'], confidence: 0.9 }), /hair buildup and visible damage/)
})
