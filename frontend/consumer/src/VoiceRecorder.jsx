import React, { useEffect, useRef, useState } from 'react'
import { createVoiceRecorder, MAX_RECORDING_SECONDS } from './voiceRecorder.js'

export default function VoiceRecorder({ onSend, onCancel }) {
  const recorder = useRef(null)
  const [state, setState] = useState('requesting'), [seconds, setSeconds] = useState(0)
  const [blob, setBlob] = useState(null), [url, setUrl] = useState(''), [error, setError] = useState('')
  useEffect(() => {
    const capture = createVoiceRecorder({
      getUserMedia: navigator.mediaDevices?.getUserMedia?.bind(navigator.mediaDevices),
      Recorder: window.MediaRecorder, onState: setState, onSeconds: setSeconds,
      onReady: setBlob, onError: setError })
    recorder.current = capture; capture.start()
    return () => capture.dispose()
  }, [])
  useEffect(() => {
    if (!blob) return
    const preview = URL.createObjectURL(blob); setUrl(preview)
    return () => URL.revokeObjectURL(preview)
  }, [blob])
  function send() {
    if (!blob) return
    const extension = { 'audio/mp4': 'm4a', 'audio/webm': 'webm', 'audio/ogg': 'ogg' }[blob.type]
    onSend(new File([blob], `voice-${Date.now()}.${extension}`, { type: blob.type }))
  }
  return <section className="voice-recorder" aria-label="Record your explanation">
    <strong>Describe your problem by voice</strong>
    <p role="status">{state === 'requesting' ? 'Allow microphone access to start recording…' : state === 'recording'
      ? `● Recording ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} · max ${MAX_RECORDING_SECONDS / 60} minutes`
      : state === 'stopping' ? 'Preparing preview…' : state === 'preview' ? 'Listen before sending. Nothing is uploaded until you send.' : 'Recording unavailable'}</p>
    {error && <p role="alert">{error}</p>}
    {url && <audio controls src={url} />}
    <div className="voice-actions">
      {state === 'recording' && <button type="button" onClick={() => recorder.current.stop()}>Stop recording</button>}
      {state === 'preview' && <button type="button" onClick={send}>Send recording</button>}
      <button type="button" onClick={onCancel}>{state === 'error' ? 'Close' : 'Cancel'}</button>
    </div>
  </section>
}
