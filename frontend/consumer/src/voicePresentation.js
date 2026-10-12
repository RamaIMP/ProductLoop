export function voicePresentation(extraction) {
  const speech = extraction?.speech
  if (!speech) return {
    message: 'I couldn’t interpret your voice message reliably. Could you record it again or type your message?',
    wait: true, spokenMessage: '',
  }
  if (speech.status !== 'understood' || !speech.message?.trim()) return {
    message: 'I couldn’t hear your words clearly. Could you record again or type your message?',
    wait: true, spokenMessage: '',
  }
  const wait = !['specific_problem', 'question'].includes(speech.intent)
  const fallback = speech.intent === 'greeting' ? 'Hi! How can I help with your shaver?'
    : 'I understand you’re having an issue with your shaver. What’s happening?'
  return { message: speech.reply?.trim() || fallback, wait, spokenMessage: speech.message.trim() }
}
