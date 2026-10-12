import test from 'node:test'
import assert from 'node:assert/strict'
import { createVoiceRecorder, recordingMime } from './voiceRecorder.js'

function fixture(getMedia) {
  let stopped=0, tick, time=0, instance
  const states=[], ready=[], errors=[]
  class Recorder {
    static isTypeSupported(type) { return type.startsWith('audio/webm') }
    constructor(stream, options) { this.mimeType=options.mimeType;this.state='inactive';instance=this }
    start() { this.state='recording' }
    stop() { this.state='inactive';this.ondataavailable({data:new Blob(['voice'])});this.onstop() }
  }
  const stream={getTracks:()=>[{stop:()=>stopped++}]}
  const capture=createVoiceRecorder({getUserMedia:getMedia|| (async()=>stream),Recorder,
    onState:s=>states.push(s),onReady:b=>ready.push(b),onError:e=>errors.push(e),onSeconds:()=>{},
    now:()=>time,schedule:fn=>{tick=fn;return 1},cancelTimer:()=>{}})
  return {capture,states,ready,errors,stream,stopped:()=>stopped,tick:()=>tick(),time:t=>time=t,instance:()=>instance}
}
test('recording produces preview only after stop and releases microphone',async()=>{
  const f=fixture();await f.capture.start();assert.equal(f.ready.length,0)
  f.capture.stop();assert.equal(f.ready[0].type,'audio/webm');assert.ok(f.stopped()>0)
  assert.equal(f.states.at(-1),'preview')
})
test('cancel discards recording',async()=>{
  const f=fixture();await f.capture.start();f.capture.dispose()
  assert.equal(f.ready.length,0);assert.ok(f.stopped()>0)
})
test('permission rejection is actionable',async()=>{
  const f=fixture(async()=>{throw Object.assign(Error(),{name:'NotAllowedError'})})
  await f.capture.start();assert.match(f.errors[0],/permission was denied/)
})
test('cancel during permission prompt releases subsequently granted stream',async()=>{
  let grant
  const f=fixture(()=>new Promise(resolve=>grant=resolve))
  const pending=f.capture.start();f.capture.dispose();grant(f.stream);await pending
  assert.equal(f.ready.length,0);assert.ok(f.stopped()>0)
})
test('two-minute limit stops and offers preview',async()=>{
  const f=fixture();await f.capture.start();f.time(120000);f.tick()
  assert.equal(f.states.at(-1),'preview');assert.equal(f.ready.length,1)
})
test('selects Safari-compatible MP4 when WebM is unavailable',()=>{
  assert.equal(recordingMime({isTypeSupported:type=>type==='audio/mp4'}),'audio/mp4')
})
test('oversized recording is discarded',async()=>{
  const f=fixture();await f.capture.start()
  f.instance().ondataavailable({data:{size:16*1024*1024}})
  assert.match(f.errors[0],/15 MiB/);assert.equal(f.ready.length,0)
})
