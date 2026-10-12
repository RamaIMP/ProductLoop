// Use this upload's findings, not the accumulated session symptoms.
export function hasClearMediaFinding(extraction) {
  return (extraction?.symptoms || []).some(symptom =>
    !['unclear_description', 'multiple_unresolved_symptoms'].includes(symptom))
}

export function mediaStorageNotice(status) {
  if (status === 'uploaded') return 'Your file has been saved to support a more detailed review of your issue.'
  if (status === 'pending') return 'We’re saving this file to support a more detailed review of your issue.'
  if (status === 'failed') return 'Your file could not be saved for further review. Please retry the upload.'
  return 'We couldn’t confirm whether your file was saved for further review.'
}

export function mediaSummary(extraction) {
  const symptoms = (extraction?.symptoms || []).filter(symptom =>
    !['unclear_description', 'multiple_unresolved_symptoms'].includes(symptom))
  if (!symptoms.length) return 'I couldn’t identify a clear issue from this file. Could you describe what you noticed?'
  const findings = symptoms.map(symptom => symptom.replaceAll('_', ' '))
  const description = findings.length === 1 ? findings[0]
    : `${findings.slice(0, -1).join(', ')} and ${findings.at(-1)}`
  const prefix = extraction.confidence < 0.7
    ? 'The analysis is uncertain, but this file may indicate'
    : 'Based on this file, the analysis suggests'
  return `${prefix} ${description}.`
}
