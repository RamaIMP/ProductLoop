import { guidancePresentation } from './guidancePresentation.js'

export function stageAfterResponse(result) {
  if (result.action === 'stop_use' || result.derived?.safety_flag) return 'safety'
  if (result.action === 'guidance_unavailable') return 'guidance-unavailable'
  if (result.action === 'ask_onset') return 'onset'
  if (['edit_report', 'add_details'].includes(result.action)) return 'initial'
  if (result.action === 'confirm_report') return 'confirm'
  if (result.action === 'ticket_confirm') return 'ticket-confirm'
  if (['resolved', 'ticket_raised'].includes(result.report?.status)) return 'done'
  // A saved record alone does not mean the user has received a remedy.
  if (result.report && guidancePresentation(result)) return 'guidance'
  return 'initial'
}

export function quickReplies(stage, followUp, busy, error) {
  if (busy || error) return []
  if (stage === 'onset') return followUp?.replies || []
  if (stage === 'guidance') return ['That fixed it', 'Still not fixed']
  if (stage === 'ticket-confirm') return ['Create ticket', 'Add more details']
  return []
}
