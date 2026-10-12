import config from '../../../shared/greetings.json' with { type: 'json' }

const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const phrase = `(?:${config.phrases.map(escape).join('|')})(?: (?:${config.addressees.map(escape).join('|')}))?`
const greeting = new RegExp(`^(?:${phrase})(?: ${phrase})*$`)

export function greetingReply(message) {
  const text = message.toLowerCase().replace(/['’]/g, '').replace(/[.,!?:;👋]/gu, ' ').replace(/\s+/g, ' ').trim()
  if (text !== '' && greeting.test(text)) {
    return config.replies.find(rule => rule.contains.some(term => text.includes(term)))?.message || config.default_reply
  }
  if (message.trim() === '👋') return config.default_reply
  return null
}
