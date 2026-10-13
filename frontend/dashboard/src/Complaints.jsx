import React,{useEffect,useState} from 'react'
import { authenticatedFetch as fetch } from './auth.jsx'
import ReviewWindow from './ReviewWindow.jsx'
import {downloadCsv} from './export.js'
import {cachedReview,readReview} from './reviewCache.js'
const API=import.meta.env.VITE_API_BASE_URL||'http://127.0.0.1:8000'
const label=v=>v==null?'Not recorded':String(v).replaceAll('_',' ')
const date=v=>v?new Date(v).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}):'Not recorded'
function useRead(path){
  const [state,set]=useState(()=>cachedReview(path)?{data:cachedReview(path),loading:false}:{loading:true})
  useEffect(()=>{let active=true;const cached=cachedReview(path);set(cached?{data:cached,loading:false}:{loading:true});readReview(path,async()=>{const r=await fetch(API+path);const data=await r.json();if(!r.ok)throw Error(data.detail||'Unable to load');return data}).then(data=>{if(active)set({data,loading:false})}).catch(e=>{if(active)set({error:e.message,loading:false})});return()=>{active=false}},[path])
  return state
}
function Media({complaintId,evidence}){
  const [show,setShow]=useState(false),[error,setError]=useState('')
  const [url,setUrl]=useState('')
  useEffect(()=>{
    if(!show)return
    const controller=new AbortController();let objectUrl;let active=true
    setError('');setUrl('')
    fetch(API+'/api/dashboard/complaints/'+encodeURIComponent(complaintId)+'/evidence/'+encodeURIComponent(evidence.evidence_id)+'/media',{signal:controller.signal})
      .then(async response=>{if(!response.ok)throw Error('Media access denied or unavailable');return response.blob()})
      .then(blob=>{if(active){objectUrl=URL.createObjectURL(blob);setUrl(objectUrl)}})
      .catch(err=>{if(active&&err.name!=='AbortError')setError(err.message)})
    return()=>{active=false;controller.abort();if(objectUrl)URL.revokeObjectURL(objectUrl)}
  },[show,complaintId,evidence.evidence_id])
  return <div className="evidence-item"><b>{label(evidence.kind)} · {evidence.evidence_id}</b><p>{evidence.extracted_summary||'No extracted findings recorded.'}</p><p className="notice">Extraction: {label(evidence.extraction_status)} · Model: {label(evidence.extraction_model)}</p>{!show?<button className="ghost" onClick={()=>setShow(true)}>Open private media</button>:<><button className="ghost" onClick={()=>{setShow(false);setError('')}}>Close media</button>{error?<p role="alert">{error}</p>:!url?<p role="status">Loading private media…</p>:evidence.content_type?.startsWith('image/')?<img src={url} alt="Complaint evidence" onError={()=>setError('Preview unavailable. Check storage access or file format.')}/>:evidence.content_type?.startsWith('audio/')?<audio controls src={url} onError={()=>setError('Audio preview unavailable.')}/>:evidence.content_type?.startsWith('video/')?<video controls src={url} onError={()=>setError('Video preview unavailable.')}/>:<p>Preview is unavailable for this file type.</p>}</>}</div>
}
function Detail({id,onClose}){
  const {data,loading,error}=useRead('/api/dashboard/complaints/'+encodeURIComponent(id))
  const c=data?.complaint
  return <aside className="complaint-detail" aria-label="Complaint details"><div className="dhead"><h2>Complaint details</h2>{c&&<button className="ghost" onClick={()=>downloadCsv([c],id+'-complaint.csv')}>Export complaint CSV</button>}<button className="ghost" onClick={onClose}>Back to complaints</button></div>{loading?<p role="status">Loading details…</p>:error?<p role="alert">{error}</p>:<><p className="notice">{c.complaint_id} · {date(c.created_at)} IST</p><h3>Summary</h3><p>{c.complaint_summary||'No summary recorded.'}</p><dl className="facts">{[['Product',c.product_model],['Serial',c.serial_number],['Batch',c.batch_reference],['Registration region',c.region],['Symptoms',c.symptoms?.join(', ')],['Severity',c.severity],['Safety flag',c.safety_flag?'Yes':'No'],['Status',c.status],['Guidance outcome',c.guidance_outcome],['Ticket',c.ticket_id],['Resolved',date(c.resolved_at)]].map(([k,v])=><React.Fragment key={k}><dt>{k}</dt><dd>{label(v)}</dd></React.Fragment>)}</dl>{c.callback&&<p>Callback: {label(c.callback.status)} · {date(c.callback.scheduled_start)}</p>}{c.service_appointment&&<details><summary>Service appointment</summary><pre>{typeof c.service_appointment==='string'?c.service_appointment:JSON.stringify(c.service_appointment,null,2)}</pre></details>}<div className="section-heading"><h3>Supporting evidence ({data.evidence.length})</h3><button className="ghost" disabled={!data.evidence.length} onClick={()=>downloadCsv(data.evidence.map(e=>({complaint_id:id,...e})),id+'-evidence.csv')}>Export evidence CSV</button></div>{!data.evidence.length?<p>No shared evidence attached.</p>:data.evidence.map(e=><Media key={e.evidence_id} complaintId={id} evidence={e}/>)}<div className="section-heading"><h3>Timeline</h3><button className="ghost" disabled={!data.events.length} onClick={()=>downloadCsv(data.events.map(e=>({complaint_id:id,...e})),id+'-timeline.csv')}>Export timeline CSV</button></div>{!data.events.length?<p>No events recorded.</p>:<ol className="event-timeline">{data.events.map(e=><li key={e.event_id}><b>{label(e.event_type)}</b><small>{date(e.occurred_at)} IST</small>{(e.previous_status||e.new_status)&&<span>{label(e.previous_status)} → {label(e.new_status)}</span>}{e.new_classification&&<span>{label(e.new_classification.issue_type)} · {label(e.new_classification.severity)}</span>}</li>)}</ol>}</>}</aside>
}
export default function Complaints({signal,region,onClose}){
  const [period,setPeriod]=useState('current'),[page,setPage]=useState(1),[selected,setSelected]=useState(null),[exporting,setExporting]=useState(false),[exportError,setExportError]=useState('')
  const start=period==='current'?signal.window_start:signal.baseline_start,end=period==='current'?signal.window_end:signal.baseline_end
  const params=new URLSearchParams({issue_type:signal.issue_type,start_date:start,end_date:end,region:region||'',page:String(page),page_size:'10'})
  const {data,loading,error}=useRead('/api/dashboard/complaints?'+params)
  const expected=period==='current'?signal.current_count:signal.prior_count
  async function exportAll(){
    setExporting(true);setExportError('')
    try{
      const rows=[];let total=null
      for(let n=1;;n++){
        const q=new URLSearchParams(params);q.set('page',n);q.set('page_size','50')
        const response=await fetch(API+'/api/dashboard/complaints?'+q)
        const result=await response.json();if(!response.ok)throw Error(result.detail||'Export failed')
        if(total!==null&&total!==result.total)throw Error('Data changed during export. Please retry.')
        total=result.total;rows.push(...result.complaints)
        if(rows.length>=total)break
        if(!result.complaints.length)throw Error('Incomplete export. Please retry.')
      }
      if(new Set(rows.map(r=>r.complaint_id)).size!==rows.length)throw Error('Data changed during export. Please retry.')
      if(!rows.length)throw Error('No matching complaints to export.')
      downloadCsv(rows.map(r=>({issue_type:signal.issue_type,selected_region:region||'All regions',period,start_date:start,end_date:end,time_zone:'Asia/Kolkata',...r})),'complaints-'+signal.issue_type+'-'+start+'-'+end+'.csv')
    }catch(e){setExportError(e.message)}finally{setExporting(false)}
  }
  return <ReviewWindow onClose={()=>selected?setSelected(null):onClose()} onExit={onClose} viewKey={selected}>{selected?<Detail key={selected} id={selected} onClose={()=>setSelected(null)}/>:<section className="card complaint-review"><div className="dhead"><h2>Underlying complaints · {label(signal.issue_type)}</h2><button className="ghost" disabled={loading||exporting||!data?.total} onClick={exportAll}>{exporting?'Exporting…':'Export all matching CSV'}</button></div><div className="filters"><div className="period-toggle" role="group" aria-label="Complaint comparison period">{['current','previous'].map(p=><button key={p} disabled={exporting} aria-pressed={period===p} onClick={()=>{setPeriod(p);setPage(1);setSelected(null)}}>{label(p)} period</button>)}</div><span className="notice">{start}–{end} · {region||'All regions'} · India time</span></div>{exportError&&<p role="alert">{exportError}</p>}{loading?<p role="status">Loading complaints…</p>:error?<p role="alert">{error}</p>:<><p className="notice">{data.total} matching complaints · signal snapshot: {expected}{data.total!==expected?' — Data changed since the snapshot; refresh signals to reconcile.':''}</p><div className="complaint-table"><table><thead><tr>{['Complaint / summary','Reported','Severity','Status','Evidence',''].map((h,i)=><th key={i}>{h}</th>)}</tr></thead><tbody>{data.complaints.map(c=><tr key={c.complaint_id}><td><b>{c.complaint_id}</b><p>{c.complaint_summary||c.symptoms?.map(label).join(', ')||'No summary'}</p></td><td>{date(c.created_at)}</td><td>{label(c.severity)}{c.safety_flag&&<span className="safety-chip"> · Safety</span>}</td><td>{label(c.status)}</td><td>{c.evidence_count}</td><td><button className="ghost" onClick={()=>setSelected(c.complaint_id)}>View details</button></td></tr>)}</tbody></table></div>{!data.total&&<p>No complaints in this period.</p>}<div className="filters"><button className="ghost" disabled={page===1} onClick={()=>setPage(page-1)}>Previous page</button><span>Page {page} of {Math.max(1,Math.ceil(data.total/10))}</span><button className="ghost" disabled={page*10>=data.total} onClick={()=>setPage(page+1)}>Next page</button></div></>}</section>}</ReviewWindow>
}
