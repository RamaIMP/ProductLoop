import { useEffect, useRef, useState } from 'react'
import { greetingReply } from './greetings'
import { formatSystemTime, watchSystemTime } from './systemClock.js'
import VoiceRecorder from './VoiceRecorder.jsx'
import { voicePresentation } from './voicePresentation.js'
import { mediaSummary, mediaStorageNotice, hasClearMediaFinding } from './mediaSummary'
import { guidancePresentation } from './guidancePresentation'
import { stageAfterResponse, quickReplies } from './conversationStage'
import UserGuide from './UserGuide.jsx'
import Services from './Services'
import { prepareServiceReport } from './serviceReport.js'
import Profile from './Profile'
import { ReportCard, ReportNav, ReportsPage, ReportDetails } from './Reports'
import { newestReports } from './reportPresentation'
import { authenticatedFetch } from './auth.jsx'

const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const WELCOME = 'Welcome to ProductLoop X500 support! How can I help you today? Feel free to describe your issue or send a picture or video.'

export default function App({ user }) {
  const USER = user.uid
  const [page, setPage] = useState('home')
  const [serviceReturnPage, setServiceReturnPage] = useState('home')
  const [stage, setStage] = useState('initial')
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [draft, setDraft] = useState({ message: '', onset: null, cleaning: null, attachments: [] })
  const [extraction, setExtraction] = useState(null)
  const [derived, setDerived] = useState(null)
  const [safetyAdvice, setSafetyAdvice] = useState(null)
  const [followUp, setFollowUp] = useState(null)
  const [report, setReport] = useState(null)
  const [reports, setReports] = useState([])
  const [reportsLoading, setReportsLoading] = useState(false)
  const [reportsError, setReportsError] = useState('')
  const [selectedReportId, setSelectedReportId] = useState(null)
  const [reportReturnPage, setReportReturnPage] = useState('home')
  const [leaveHomePrompt, setLeaveHomePrompt] = useState(false)
  const [callbackOpen, setCallbackOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [busyMessage, setBusyMessage] = useState('Preparing your response…')
  const turnLock = useRef(false)
  const [error, setError] = useState('')
  const [uploads, setUploads] = useState({})
  const incidentId = useRef(null)
  const [callbackSlots, setCallbackSlots] = useState([])
  useEffect(() => {
    let stopped = false
    const timer = setTimeout(async () => {
      for (const upload of Object.values(uploads).filter(item => item.storage_status === 'pending')) {
        try {
          const response = await authenticatedFetch(`${API}/api/media/${upload.evidence_id}/status?user_id=${encodeURIComponent(USER)}`)
          const result = await response.json()
          if (!response.ok) throw new Error(result.detail || 'Storage status unavailable')
          if (stopped) return
          setUploads(previous => ({ ...previous, [upload.evidence_id]: { ...upload, ...result, error: result.error || null } }))
        } catch (err) {
          if (stopped) return
          setUploads(previous => ({ ...previous, [upload.evidence_id]: { ...upload, storage_status: 'unknown', error: `Save could not be verified: ${err.message}` } }))
        }
      }
    }, 1500)
    return () => { stopped = true; clearTimeout(timer) }
  }, [uploads])
  const end = useRef(null)
  useEffect(() => {
    // Some browsers return a Promise from scrollIntoView; effects must not return it.
    end.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, stage])
  const add = (...items) => setMessages(previous => [...previous, ...items])
  const api = async (path, options = {}) => {
    const response = await authenticatedFetch(`${API}${path}`, options)
    const output = await response.json()
    if (!response.ok) throw new Error(output.detail || 'Request failed')
    return output
  }
  const loadReports = async () => {
    setReportsLoading(true); setReportsError('')
    try { setReports(await api(`/api/reports?user_id=${encodeURIComponent(USER)}`)) }
    catch (err) { setReportsError(`Could not load your reports. ${err.message}`) }
    finally { setReportsLoading(false) }
  }
  const goHome = async () => {
    setPage('home')
    await loadReports()
  }
  const goServices = () => {
    setServiceReturnPage(page)
    setPage('services')
  }
  const safetyServices = (consentShare) => runTurn(async () => {
    const linkedReport = await prepareServiceReport({ report, ensureIncident, api,
      userId: USER, extraction, derived, consentShare })
    setReport(linkedReport)
    goServices()
  }, 'Saving your report…')
  const goReports = () => setPage('reports')
  const goProfile = () => setPage('profile')
  const openReport = id => { setSelectedReportId(id); setReportReturnPage(page); setPage('report-detail') }
  const hasUnsubmittedReport = !report && Boolean(extraction || draft.message || draft.attachments.length)
  const requestHome = () => {
    if (hasUnsubmittedReport) { setLeaveHomePrompt(true); return }
    goHome()
  }
  const discardAndGoHome = () => runTurn(async () => {
    if (incidentId.current) await api(`/api/incidents/${incidentId.current}/abandon?user_id=${encodeURIComponent(USER)}`, { method: 'POST' })
    incidentId.current = null
    setLeaveHomePrompt(false)
    setExtraction(null); setDerived(null); setFollowUp(null)
    setDraft({ message: '', onset: null, cleaning: null, attachments: [] })
    goHome()
  })
  useEffect(() => { if (page === 'home' || page === 'reports') loadReports() }, [page])
  const bot = text => ({ from: 'bot', text })
  const mine = text => ({ from: 'me', text })
  const ensureIncident = async () => {
    if (!incidentId.current) incidentId.current = `PL-${crypto.randomUUID()}`
    await api('/api/incidents', { method: 'POST', body: JSON.stringify({
      user_id: USER, complaint_id: incidentId.current,
    }) })
    return incidentId.current
  }
  const converse = async (message, overrides = {}) => {
    await ensureIncident()
    const history = (overrides.history || messages)
      .filter(item => ['me', 'bot'].includes(item.from))
      .map(item => ({ role: item.from === 'me' ? 'user' : 'assistant', text: item.text }))
    const result = await api('/api/conversation', { method: 'POST', body: JSON.stringify({
      user_id: USER, complaint_id: incidentId.current, message, history, extraction, report_id: report?.report_id, ...overrides,
    }) })
    setSafetyAdvice(result.response || null)
    if (result.message) add({ ...bot(result.message), sources: result.sources || [], guidance: guidancePresentation(result) })
    setFollowUp(result.follow_up || null)
    if (result.extraction) {
      setExtraction(result.extraction)
      setDraft(d => ({ ...d, message: d.message || message,
        onset: result.extraction.context.onset.replaceAll('_', ' '),
        cleaning: result.extraction.context.persists_after_cleaning.replaceAll('_', ' ') }))
    }
    if (result.derived) setDerived(result.derived)
    if (result.report) setReport(result.report)
    setStage(stageAfterResponse(result))
  }
  const runTurn = async (task, loadingMessage = 'Preparing your response…') => {
    if (turnLock.current) return
    turnLock.current = true; setBusyMessage(loadingMessage); setBusy(true); setError('')
    try { await task() }
    catch (err) { setError(err.message) }
    finally {
      turnLock.current = false; setBusy(false)
    }
  }
  const goChat = () => runTurn(async () => {
    incidentId.current = null; setUploads({})
    setPage('chat'); setStage('initial'); setLeaveHomePrompt(false); setCallbackOpen(false)
    setExtraction(null); setDerived(null); setFollowUp(null); setReport(null); setText('')
    setDraft({ message: '', onset: null, cleaning: null, attachments: [] }); setMessages([bot(WELCOME)])
  })
  const send = (value, event = 'message') => {
    const message = value.trim()
    if (!message || turnLock.current) return
    const greeting = greetingReply(message)
    if (greeting) {
      setText(''); setError('')
      add(mine(message), bot(greeting))
      return
    }
    return runTurn(async () => {
      setText(''); add(mine(message))
      await converse(message, { event })
    })
  }
  const attach = (kind, file) => runTurn(async () => {
    if (!file.size || file.size > 15 * 1024 * 1024) { setError('Choose a non-empty media file up to 15 MiB.'); return }
    const label = `${kind}: ${file.name}`
    const previewUrl = URL.createObjectURL(file)
    setDraft(d => ({ ...d, attachments: [...d.attachments, label] }))
    add({ from: 'attachment', kind, fileName: file.name, mimeType: file.type, previewUrl })
    try {
      await ensureIncident()
      const form = new FormData()
      form.append('file', file)
      form.append('audio_purpose', kind === 'Voice' ? 'spoken_complaint' : kind === 'Sound' ? 'device_sound' : 'general')
      form.append('user_id', USER)
      form.append('complaint_id', incidentId.current)
      form.append('evidence_id', `ev_${crypto.randomUUID().replaceAll('-', '')}`)
      form.append('message', [draft.message, text].filter(Boolean).join('\n'))
      form.append('prior_symptoms_json', JSON.stringify(extraction?.symptoms || []))
      const response = await authenticatedFetch(`${API}/api/media/extract`, { method: 'POST', body: form })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Media analysis failed')
      if (data.storage) setUploads(previous => ({ ...previous, [data.evidence_id]: { ...data.storage, filename: file.name } }))
      if (data.analysis_mode !== 'multimodal_gemini') throw new Error('Media analysis is unavailable. Please retry the upload.')
      // Show the findings BEFORE the onset question; never attribute earlier
      // session evidence to the newly uploaded file.
      const voice = kind === 'Voice' ? voicePresentation(data.media_extraction) : null
      const findingsMessage = voice ? voice.message : mediaSummary(data.media_extraction)
      if ((voice ? voice.wait : !hasClearMediaFinding(data.media_extraction)) && !data.derived.safety_flag) {
        add({ ...bot(findingsMessage), evidenceId: data.evidence_id })
        setExtraction(data.extraction); setDerived(data.derived)
        setFollowUp(null); setStage('initial')
        return // Wait for the user; no automatic conversation call or next-step loader.
      }
      setBusyMessage('Preparing next step…')
      add({ ...bot(findingsMessage), evidenceId: data.evidence_id })
      setExtraction(data.extraction); setDerived(data.derived)
      if (data.derived.safety_flag) { setSafetyAdvice(null); setStage('safety') }
      const mediaHistory = [...messages, bot(findingsMessage)]
        .filter(item => ['me', 'bot'].includes(item.from))
        .map(item => ({ role: item.from === 'me' ? 'user' : 'assistant', text: item.text }))
      await converse(voice?.spokenMessage || text || '', { event: 'media_added', extraction: data.extraction, history: mediaHistory })
    } catch (err) {
      setError(`Could not analyse the media or continue the conversation. ${err.message}`)
    }
  }, 'Analysing your media…')
  const confirm = () => runTurn(async () => {
    await ensureIncident()
    const data = await api('/api/reports/confirm', { method: 'POST', body: JSON.stringify({ user_id: USER, complaint_id: incidentId.current, consent_share: true, extraction, derived }) })
    setReport(data.report); setStage('awaiting-guidance')
    add(mine('Looks right — submit my report'))
    await converse('I confirmed my report.', { event: 'report_confirmed', report_id: data.report.report_id })
  })
  const requestCallback = slot => runTurn(async () => {
    try {
      const updated = await api(`/api/reports/${report.report_id}/callback`, { method: 'POST', body: JSON.stringify({ slot: slot.label, user_id: USER, scheduled_start: slot.scheduled_start, scheduled_end: slot.scheduled_end, time_zone: slot.time_zone }) })
      setReport(updated); setCallbackOpen(false)
      add(mine(slot.label))
      await converse(slot.label, { event: 'callback_requested' })
    } catch (err) { setError(`Could not request a callback. ${err.message}`) }
  })
  const openCallback = () => runTurn(async () => {
    setCallbackSlots(await api('/api/callback-slots')); setCallbackOpen(open => !open)
  })
  const chips = quickReplies(stage, followUp, busy, error)
  const chipAction = choice => send(choice, {
    'Today': 'onset_selected', 'This week': 'onset_selected', 'Longer ago': 'onset_selected',
    'That fixed it': 'resolved', 'Still not fixed': 'not_resolved',
    'Create ticket': 'create_ticket', 'Add more details': 'add_details',
  }[choice] || 'message')
  const title = report ? `Report ${report.report_id}` : stage === 'safety' ? 'Safety check active' : stage === 'confirm' ? 'Check your report' : 'Report a problem'
  return <div className="stage-wrap"><div className="phone"><div className="screen"><div className="notch" />
    {page === 'home' ? <Home goProfile={goProfile} busy={busy} goChat={goChat} goServices={goServices} goReports={goReports} openReport={openReport} reports={reports} loading={reportsLoading} error={reportsError} retry={loadReports} /> : page === 'reports' ? <ReportsPage goProfile={goProfile} reports={reports} loading={reportsLoading} error={reportsError} retry={loadReports} openReport={openReport} goHome={goHome} goReports={loadReports} goServices={goServices} /> : page === 'profile' ? <Profile api={api} userId={USER} goHome={goHome} goReports={goReports} goServices={goServices} goProfile={goProfile} /> : page === 'report-detail' ? <ReportDetails reportId={selectedReportId} userId={USER} api={api} back={() => setPage(reportReturnPage)} goHome={goHome} /> : page === 'services' ? <div className="page service-page"><Status light /><div className="appbar"><button className="back" aria-label="Back to previous page" onClick={() => setPage(serviceReturnPage)}>‹</button><div><b>Nearby service centres</b><small>Service centre finder</small></div><HomeButton onClick={requestHome} /></div><div className="service-page-content">{leaveHomePrompt && <LeaveHome stay={() => setLeaveHomePrompt(false)} discard={discardAndGoHome} />}<Services api={api} userId={USER} reportId={serviceReturnPage === 'chat' ? report?.report_id : undefined} done={goHome} /></div></div> : <div className="page chat-page"><Status light /><div className="appbar"><button className="back" onClick={requestHome}>‹</button><div><b>{title}</b><small>{report ? 'Report submitted' : stage === 'confirm' ? 'Draft saved · confirm to submit' : 'Tell us in your own words'}</small></div><HomeButton onClick={requestHome} /></div><div className="prog"><i style={{ width: stage === 'confirm' ? '80%' : report ? '100%' : stage === 'followup' ? '55%' : '30%' }} /></div>
      <div className="messages">{messages.map((message, index) => <Bubble key={index} message={message} storageStatus={uploads[message.evidenceId]?.storage_status} />)}
        {leaveHomePrompt && <LeaveHome stay={() => setLeaveHomePrompt(false)} discard={discardAndGoHome} />}
        {stage === 'confirm' && <Confirm draft={draft} extraction={extraction} derived={derived} followUp={followUp} confirm={confirm} reset={() => send('I want to correct my report.', 'edit_report')} busy={busy} />}
        {stage === 'safety' && <Safety advice={safetyAdvice} openServices={safetyServices} busy={busy} submitted={Boolean(report)} />}
        {stage === 'guidance-unavailable' && !busy && <div className="quick-replies"><button onClick={() => report ? runTurn(() => converse('Please retry the troubleshooting guidance.', { event: 'report_confirmed', report_id: report.report_id })) : send('Please retry the troubleshooting guidance for my question.')}>Try again</button><button onClick={goServices}>Contact support</button></div>}
        {stage === 'awaiting-guidance' && error && !busy && report && <div className="quick-replies"><button onClick={() => runTurn(() => converse('I confirmed my report.', { event: 'report_confirmed', report_id: report.report_id }))}>Retry guidance</button></div>}
        {chips.length > 0 && <div className="quick-replies">{chips.map(chip => <button key={chip} disabled={busy} onClick={() => chipAction(chip)}>{chip}</button>)}</div>}
        {stage === 'done' && report?.status === 'ticket_raised' && !report.callback && <><div className="exit-actions"><button disabled={busy} onClick={openCallback}>☎️ {report.callback ? 'Callback requested' : 'Request a callback'}</button><button onClick={goServices}>📍 Find service centre</button><a target="_blank" rel="noreferrer" href={`https://mail.google.com/mail/?view=cm&fs=1&to=support%40productloop.demo&su=${encodeURIComponent(`ProductLoop ${report?.ticket_id || report?.report_id || ''}`)}`}>✉️ Email support</a></div>{callbackOpen && <CallbackSlots slots={callbackSlots} choose={requestCallback} />}</>}
        {busy && <div role="status" className="message bot">{busyMessage}</div>}<div ref={end} /></div>{Object.values(uploads).filter(upload => ['failed', 'unknown'].includes(upload.storage_status) && !messages.some(message => message.evidenceId === upload.evidence_id)).map(upload => <p role="status" key={upload.evidence_id}>{upload.filename}: {upload.storage_status === 'uploaded' ? 'File saved' : upload.storage_status === 'pending' ? 'Saving file in background…' : upload.error || 'File was not saved. Please retry upload.'}</p>)}{error && <p className="error">{error}</p>}<Composer text={text} setText={setText} send={send} attach={attach} disabled={busy} />
    </div>}</div></div><p className="prototype-note">ProductLoop · X500 support</p>
      <UserGuide />
    </div>
}

function Status({ light = false }) {
  const [time, setTime] = useState(() => formatSystemTime())
  useEffect(() => watchSystemTime(setTime), [])
  return <div className={`status ${light ? 'light' : 'white'}`}><span aria-label="Current device time">{time}</span><span>5G ▮▮▮</span></div>
}
function Home({ goProfile, busy, goChat, goServices, goReports, openReport, reports, loading, error, retry }) {
  return <div className="page home-page"><Status />
    <div className="hero"><div className="top"><div className="brand"><span className="logo">⟳</span>ProductLoop</div></div><p>Welcome, {user.name || 'there'}</p><h2>Having a problem with your product?</h2></div>
    <div className="home-scroll">
      <div className="cta"><div className="product-row"><span className="product-icon">🪒</span><div><b>X500 Electric Shaver</b><small>Product support</small></div></div><button className="big" disabled={busy} onClick={goChat}>Report a problem</button><p>Tell us what's wrong. We'll ask a few quick questions.</p></div>
      <div className="section-title"><b>My reports</b><button type="button" onClick={goReports}>View all ({reports.length})</button></div>
      {loading && <p role="status">Loading reports…</p>}
      {error && <p role="alert">{error} <button onClick={retry}>Retry</button></p>}
      {!loading && !error && !reports.length && <p className="empty-reports">No reports yet. When you report an issue, it will appear here.</p>}
      {newestReports(reports, 3).map(report => <ReportCard key={report.report_id} report={report} onOpen={openReport} />)}
      <button className="svc" type="button" onClick={goServices}><span>📍</span><div><b>Find nearby service centres</b><small>Search near your location →</small></div></button>
    </div><ReportNav goProfile={goProfile} active="home" goHome={() => {}} goReports={goReports} goServices={goServices} />
  </div>
}
function Section({ title, link }) { return <div className="section-title"><b>{title}</b><a>{link}</a></div> }
function Bubble({ message, storageStatus }) {
  if (message.guidance) return <div className="guide-card" role="region" aria-label={message.guidance.title}>
    <h4>{message.guidance.title}</h4>
    <p style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.5, margin: '8px 0' }}>{message.text}</p>
    <span>Source: {[...new Set(message.sources.map(source => source.title))].join(', ')}</span>
  </div>
  if (message.from === 'guidance') return <div className="guide-card"><h4>Try this first</h4><ol>{message.data.guidance.map(step => <li key={step}>{step}</li>)}</ol><span>Source: {message.data.sources?.[0]?.title || 'X500 knowledge base'}</span></div>
  if (message.from === 'sent' || message.from === 'ticket') return <div className="sent">{message.text}</div>
  if (message.from === 'attachment') return <div className="attachment-card"><b>{message.kind} attached</b>{message.mimeType.startsWith('image/') && <img src={message.previewUrl} alt={`Attached ${message.fileName}`} />}{message.mimeType.startsWith('video/') && <video src={message.previewUrl} controls />}{message.mimeType.startsWith('audio/') && <audio src={message.previewUrl} controls />}<small>{message.fileName}</small></div>
  return <div className={message.from === 'me' ? 'message me' : 'message bot'}><span style={{ whiteSpace: 'pre-wrap' }}>{message.text}</span>{message.evidenceId && <small role="status" style={{ display: 'block', marginTop: 10, fontSize: 12, lineHeight: 1.5, color: '#667085' }}>{mediaStorageNotice(storageStatus)}</small>}{message.sources?.length > 0 && <small style={{ display: 'block', marginTop: 8 }}>Source: {[...new Set(message.sources.map(source => source.title))].join(', ')}</small>}</div>
}
function Confirm({ draft, extraction, followUp, confirm, reset, busy }) { const followupLabel = followUp?.field === 'during_charging' ? 'During charging' : followUp ? 'After cleaning/refitting' : null; return <><div className="report-card"><h4>Your report <button onClick={reset}>Edit</button></h4><Row label="Product" value="X500 Electric Shaver" /><Row label="Symptoms" value={extraction.symptoms.map(s => s.replaceAll('_', ' ')).join(', ')} /><Row label="Started" value={draft.onset} />{followupLabel && <Row label={followupLabel} value={draft.cleaning} />}<Row label="Evidence" value={draft.attachments.length ? draft.attachments.join(', ') : 'None'} /></div><div className="consent">✓ Share this report and any attached media anonymously with the X500 quality team. No name or contact details are shared.</div><div className="confirm-buttons"><button onClick={reset}>Edit</button><button className="primary" disabled={busy} onClick={confirm}>Looks right</button></div></> }
function Row({ label, value }) { return <div className="row"><span>{label}</span><b>{value}</b></div> }
function LeaveHome({ stay, discard }) { return <div className="report-card"><h4>Leave this report?</h4><p style={{ fontSize: 13, margin: '4px 0 10px' }}>Your report has not been submitted yet. You can continue reporting or discard it and return Home.</p><div className="confirm-buttons"><button onClick={stay}>Continue reporting</button><button className="primary" onClick={discard}>Discard and go Home</button></div></div> }
function CallbackSlots({ slots, choose }) { return <div className="report-card"><h4>Choose a callback time</h4><p style={{ fontSize: 12.5, margin: '4px 0 10px' }}>Select your preferred callback time.</p><div className="quick-replies">{slots.map(slot => <button key={slot.scheduled_start} onClick={() => choose(slot)}>{slot.label}</button>)}</div></div> }
function Safety({ advice, openServices, busy, submitted }) {
  const [share, setShare] = useState(false)
  return <div className="safety-card"><h3>⚠️ {advice?.title || 'Stop using it now'}</h3><ul>{(advice?.steps || ['Stop using the shaver until the safety concern has been assessed.']).map(step => <li key={step}>{step}</li>)}</ul><p>{advice?.note || 'Contact an authorised service centre for help.'}</p>
    {!submitted && <><p>Save this report to book service for this issue.</p><label><input type="checkbox" checked={share} disabled={busy} onChange={event => setShare(event.target.checked)} /> Also share this report and attached media anonymously with the X500 quality team (optional).</label></>}
    <button disabled={busy} onClick={() => openServices(share)}>{submitted ? 'Find service centre' : 'Save report & find service centre'}</button>
  </div>
}
function Composer({ text, setText, send, attach, disabled }) {
  const [voiceOpen, setVoiceOpen] = useState(false)
  const inputs = { Photo: useRef(null), Video: useRef(null), Sound: useRef(null) }
  const config = { Photo: ['📷', 'image/*'], Video: ['🎥', 'video/*'], Sound: ['〽️', 'audio/*'] }
  const blocked = disabled || voiceOpen
  return <div className="composer"><div className="attachments"><span><button type="button" disabled={blocked} aria-label="Record a voice explanation" onClick={() => setVoiceOpen(true)}>🎙️<small>Voice</small></button></span>{Object.keys(config).map(kind => <span key={kind}><input ref={inputs[kind]} className="file-input" type="file" accept={config[kind][1]} onChange={event => { const [file] = event.target.files; if (file) attach(kind, file); event.target.value = '' }} /><button type="button" disabled={blocked} onClick={() => inputs[kind].current?.click()}>{config[kind][0]}<small>{kind}</small></button></span>)}</div>{voiceOpen && <VoiceRecorder onCancel={() => setVoiceOpen(false)} onSend={file => { setVoiceOpen(false); attach('Voice', file) }} />}<form onSubmit={event => { event.preventDefault(); if (!blocked) send(text) }}><input disabled={blocked} value={text} onChange={event => setText(event.target.value)} placeholder={voiceOpen ? 'Finish or cancel your recording…' : disabled ? 'Waiting for a reply…' : 'Type a message…'} /><button disabled={blocked}>➤</button></form></div>
}
import HomeButton from './HomeButton.jsx'
