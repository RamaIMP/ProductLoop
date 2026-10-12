import {test} from 'node:test'
import assert from 'node:assert/strict'
import {csv,exportRows} from './export.js'
test('CSV escaping, numeric negative values and formula safety',()=>{
  const result=csv([{label:'a,"b"\nc',growth:-25,empty:null,unsafe:'=SUM(A1)'}])
  assert.ok(result.startsWith('\uFEFF'))
  assert.ok(result.includes('"a,""b""\nc"'))
  assert.ok(result.includes('"-25","","\'=SUM(A1)"'))
})
test('exports snapshot scope, null baseline and paired daily dates',()=>{
  const signals=[{issue_type:'charging',window_start:'2026-10-07',window_end:'2026-10-09',baseline_start:'2026-10-04',growth_pct:null,current_count:5,trend:[{date:'2026-10-07',current:5,baseline:0,safety:1}]}]
  const summary=exportRows(signals,'India','all')
  assert.equal(summary[0].registration_region,'India')
  assert.equal(summary[0].growth_pct,null)
  assert.equal(summary[0].current_count,5)
  const daily=exportRows(signals,'India','all',true)
  assert.equal(daily[0].baseline_date,'2026-10-04')
  assert.equal(daily[0].safety_count,1)
})
