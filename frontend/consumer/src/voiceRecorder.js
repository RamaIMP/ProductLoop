export const MAX_RECORDING_SECONDS = 120
const MAX_BYTES = 15 * 1024 * 1024
export function recordingMime(Recorder) {
  return ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm', 'audio/ogg;codecs=opus']
    .find(type => Recorder.isTypeSupported(type))
}

export function createVoiceRecorder({ getUserMedia, Recorder, onState, onSeconds, onReady, onError,
  schedule = setInterval, cancelTimer = clearInterval, now = Date.now }) {
  let cancelled = false, stream, recorder, timer, chunks = [], size = 0, started
  const release = () => { if (timer) cancelTimer(timer); timer = null; stream?.getTracks().forEach(track => track.stop()) }
  const fail = message => { cancelled = true; if (recorder?.state === 'recording') recorder.stop(); release(); onError(message); onState('error') }
  async function start() {
    onState('requesting')
    try {
      if (!getUserMedia || !Recorder) throw Error('Recording is unavailable. Use HTTPS or localhost and a supported browser.')
      const mimeType = recordingMime(Recorder)
      if (!mimeType) throw Error('This browser cannot record a supported audio format. Use Sound to upload a recording.')
      stream = await getUserMedia({ audio: true })
      if (cancelled) { release(); return }
      recorder = new Recorder(stream, { mimeType })
      recorder.ondataavailable = event => {
        if (cancelled || !event.data.size) return
        size += event.data.size
        if (size > MAX_BYTES) { fail('Recording exceeded 15 MiB. Please record a shorter message.'); return }
        chunks.push(event.data)
      }
      recorder.onerror = () => fail('Recording failed. Please check your microphone and try again.')
      recorder.onstop = () => {
        release()
        if (cancelled) return
        if (!size) { fail('No audio was captured. Please try again.'); return }
        const type = recorder.mimeType.split(';')[0]
        onReady(new Blob(chunks, { type }))
        onState('preview')
      }
      recorder.start(1000); started = now(); onSeconds(0); onState('recording')
      timer = schedule(() => {
        const seconds = Math.floor((now() - started) / 1000)
        onSeconds(Math.min(seconds, MAX_RECORDING_SECONDS))
        if (seconds >= MAX_RECORDING_SECONDS) stop()
      }, 250)
    } catch (error) {
      release()
      if (cancelled) return
      const message = error.name === 'NotAllowedError' ? 'Microphone permission was denied. Allow microphone access in your browser and try again.'
        : error.name === 'NotFoundError' ? 'No microphone was found. Connect one and try again.'
        : error.name === 'NotReadableError' ? 'The microphone is busy or unavailable. Close other recording apps and try again.' : error.message
      onError(message); onState('error')
    }
  }
  function stop() { if (recorder?.state === 'recording') { onState('stopping'); recorder.stop(); release() } }
  function dispose() { cancelled = true; if (recorder?.state === 'recording') recorder.stop(); release(); chunks = [] }
  return { start, stop, dispose }
}
