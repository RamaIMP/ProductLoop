import test from 'node:test'
import assert from 'node:assert/strict'
import { debugSafe, debugBlocks } from './debugFlow.js'

test('flow orders input, executed stages, final output', () => {
  const result = debugBlocks({ input: { filename: 'test.jpg' }, status: 200, output: {
    debug: { stages: [{ stage: 'Upload', output: { gcs_uri: 'gs://private/test.jpg' } }, { stage: 'Extraction', output: { symptoms: ['hair_buildup'] } }] },
  } })
  assert.deepEqual(result.map(x => x.stage), ['Input', 'Upload', 'Extraction', 'Final output'])
})
test('private gs URI survives redaction but credentials and media preview do not', () => {
  const safe = debugSafe({ gcs_uri: 'gs://private/test.jpg', input_file_uri: 'gs://private/test.jpg',
    authorization: 'secret', api_key: 'secret', previewUrl: 'blob:media', source: '/local/private/file' })
  assert.deepEqual(safe, { gcs_uri: 'gs://private/test.jpg', input_file_uri: 'gs://private/test.jpg' })
})
test('failed and template requests never fabricate model stages', () => {
  const failed = debugBlocks({ status: 503, output: { detail: 'Unavailable' } })
  assert.equal(failed.length, 2)
  assert.equal(failed[1].status, 'error')
  const workflow = debugBlocks({ status: 200, output: { mode: 'workflow', model: null } })
  assert.equal(workflow[1].stage, 'Predefined response / state update')
})
