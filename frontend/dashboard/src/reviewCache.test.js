import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readReview,cachedReview,clearReviewCache} from './reviewCache.js'
test('reopening shares loaded data and pending requests; refresh invalidates',async()=>{
  clearReviewCache();let calls=0
  const load=async()=>{calls++;return {complaint_id:'c1'}}
  const a=readReview('detail/c1',load),b=readReview('detail/c1',load)
  assert.equal(a,b);await a
  assert.equal(cachedReview('detail/c1').complaint_id,'c1')
  await readReview('detail/c1',load);assert.equal(calls,1)
  clearReviewCache();await readReview('detail/c1',load);assert.equal(calls,2)
})
test('failed reads can retry and distinct pages stay independent',async()=>{
  clearReviewCache()
  await assert.rejects(readReview('page1',async()=>{throw Error('offline')}))
  assert.equal(await readReview('page1',async()=>1),1)
  assert.equal(await readReview('page2',async()=>2),2)
})
