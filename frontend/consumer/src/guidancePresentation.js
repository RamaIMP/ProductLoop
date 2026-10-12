export function guidancePresentation(result) {
  if (result.mode !== 'gemini_reasoning' || !result.sources?.length || !result.message
      || result.derived?.safety_flag || result.action === 'stop_use') return null
  return {
    title: result.extraction?.context?.persists_after_cleaning === 'yes' ? 'Next steps' : 'Try this first',
  }
}
