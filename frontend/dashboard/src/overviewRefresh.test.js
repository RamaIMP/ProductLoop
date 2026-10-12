import test from 'node:test'
import assert from 'node:assert/strict'
import { createOverviewRefresh, REFRESH_INTERVAL_MS } from './overviewRefresh.js'

function fixture(fetcher) {
  const data=[], errors=[], busy=[], cancelled=[]
  let tick, interval
  const reader=createOverviewRefresh({url:'/api/dashboard/overview?days=7&region=India',fetcher,
    onData:x=>data.push(x),onError:x=>errors.push(x),onBusy:x=>busy.push(x),
    schedule:(fn,ms)=>{tick=fn;interval=ms;return 42},cancel:id=>cancelled.push(id)})
  return {reader,data,errors,busy,cancelled,tick:()=>tick(),interval:()=>interval}
}
const ok=value=>({ok:true,json:async()=>value})

test('manual and five-minute automatic refresh use the same read-only endpoint',async()=>{
  const requests=[]
  const f=fixture(async url=>{requests.push(url);return ok({signals:[requests.length]})})
  assert.equal(f.interval(),300000)
  assert.equal(REFRESH_INTERVAL_MS,300000)
  await f.reader.refresh();await f.tick()
  assert.deepEqual(f.data,[{signals:[1]},{signals:[2]}])
  assert.ok(requests.every(url=>url==='/api/dashboard/overview?days=7&region=India'))
  f.reader.dispose();assert.deepEqual(f.cancelled,[42])
})

test('failed refresh retains the last successful data',async()=>{
  let count=0
  const f=fixture(async()=>{if(count++)throw Error('Offline');return ok({signals:[1]})})
  await f.reader.refresh();await f.tick()
  assert.deepEqual(f.data,[{signals:[1]}])
  assert.equal(f.errors.at(-1),'Offline')
})

test('overlapping refresh is skipped and disposed scope cannot update UI',async()=>{
  let resolve, signal, calls=0
  const f=fixture((url,opts)=>{calls++;signal=opts.signal;return new Promise(r=>resolve=r)})
  const pending=f.reader.refresh()
  await f.tick();assert.equal(calls,1)
  f.reader.dispose();assert.equal(signal.aborted,true)
  resolve(ok({signals:['old scope']}));await pending
  assert.deepEqual(f.data,[])
  await f.tick();assert.equal(calls,1)
})
