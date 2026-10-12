export function debugSafe(value) {
  if (Array.isArray(value)) return value.map(debugSafe)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value)
    .filter(([key]) => !['source', 'uri', 'url', 'previewUrl', 'authorization', 'api_key', 'token', 'history'].includes(key))
    .map(([key, item]) => [key, debugSafe(item)]))
  return value
}

export function debugBlocks(entry) {
  const failed = entry.status === 'error' || entry.status === 'network error' || Number(entry.status) >= 400
  const stages = entry.output?.debug?.stages || []
  return [
    { stage: 'Input', output: entry.input, model: null },
    ...stages,
    { stage: failed ? 'Request failed' : entry.output?.mode === 'workflow' || entry.status === 'local' || entry.output?.mode === 'instant_greeting'
      ? 'Predefined response / state update' : 'Final output',
      status: failed ? 'error' : entry.output?.analysis_mode === 'development_fallback' ? 'fallback' : 'complete',
      model: entry.output?.model || null,
      output: { ...entry.output, debug: undefined } },
  ]
}
