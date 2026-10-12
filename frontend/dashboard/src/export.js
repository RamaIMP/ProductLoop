// Export the loaded snapshot, not a second query that could return different data.
export function csv(rows) {
  if (!rows.length) return ''
  const headers=Object.keys(rows[0])
  const cell=value=>{
    let text=value==null?'':typeof value==='object'?JSON.stringify(value):String(value)
    // Prevent spreadsheet formula execution while preserving numeric negatives.
    if(typeof value==='string' && /^[\s]*[=+@-]/.test(text)) text="'"+text
    return '"'+text.replaceAll('"','""')+'"'
  }
  return '\uFEFF'+[headers,...rows.map(row=>headers.map(key=>row[key]))].map(row=>row.map(cell).join(',')).join('\r\n')+'\r\n'
}
export function exportRows(signals,region,filter,daily=false) {
  return signals.flatMap(s=>{
    const scope={product_model:s.product_model,registration_region:region||'All regions',signal_filter:filter,issue_type:s.issue_type,window_start:s.window_start,window_end:s.window_end,baseline_start:s.baseline_start,baseline_end:s.baseline_end,time_zone:s.time_zone,computed_at:s.computed_at}
    if(daily) return s.trend.map((d,i)=>({...scope,date:d.date,baseline_date:new Date(Date.parse(s.baseline_start+'T00:00:00Z')+i*86400000).toISOString().slice(0,10),current_count:d.current,prior_count:d.baseline,safety_count:d.safety}))
    return [{...scope,current_count:s.current_count,prior_count:s.prior_count,growth_pct:s.growth_pct,status:s.status,priority:s.priority,safety_count:s.safety_count,prior_safety_count:s.prior_safety_count,safety_review:s.safety_review,evidence_count:s.evidence_count,symptoms:s.symptoms,batches:s.batches,regions:s.regions,outcomes:s.outcomes,severity:s.severity}]
  })
}
export function downloadCsv(rows,filename) {
  const url=URL.createObjectURL(new Blob([csv(rows)],{type:'text/csv;charset=utf-8;'}))
  const link=document.createElement('a');link.href=url;link.download=filename
  document.body.appendChild(link);link.click();link.remove()
  setTimeout(()=>URL.revokeObjectURL(url),1000)
}
