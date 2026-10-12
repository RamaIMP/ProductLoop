import test from 'node:test'
import assert from 'node:assert/strict'
import { voicePresentation } from './voicePresentation.js'

test('clear but vague speech asks about the problem, not recording quality', () => {
  const result = voicePresentation({symptoms:['unclear_description'],speech:{status:'understood',intent:'vague_problem',message:'I have an issue with my shaver',reply:'I understand. What is happening with your shaver?'}})
  assert.equal(result.message,'I understand. What is happening with your shaver?')
  assert.equal(result.wait,true)
})
test('voice greeting greets and waits', () => {
  const result=voicePresentation({speech:{status:'understood',intent:'greeting',message:'Hi',reply:'Hi! How can I help?'}})
  assert.equal(result.message,'Hi! How can I help?');assert.equal(result.wait,true)
})
test('specific speech continues with its actual meaning and negation', () => {
  const result=voicePresentation({speech:{status:'understood',intent:'specific_problem',message:'It will not charge. There is no smoke.',reply:'Your shaver is not charging.'}})
  assert.equal(result.wait,false);assert.equal(result.spokenMessage,'It will not charge. There is no smoke.')
})
test('spoken product question continues even without a fault symptom', () => {
  const result=voicePresentation({symptoms:['unclear_description'],speech:{status:'understood',intent:'question',message:'What is the warranty?',reply:'You’re asking about the warranty.'}})
  assert.equal(result.wait,false)
})
test('unintelligible, absent or missing speech interpretation waits for user', () => {
  for (const status of ['unclear','no_speech']) {
    const result=voicePresentation({speech:{status,intent:'other',message:'',reply:'Try again'}})
    assert.equal(result.wait,true);assert.match(result.message,/hear your words clearly/)
  }
  assert.equal(voicePresentation({}).wait,true)
})
