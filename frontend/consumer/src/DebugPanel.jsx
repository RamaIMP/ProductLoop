import './debug.css'
import { debugSafe, debugBlocks } from './debugFlow'
export { debugSafe } from './debugFlow'

export default function DebugPanel({ enabled, setEnabled, entries, clear, state }) {
  return <details className="debug-panel" open>
    <summary>Developer debug · {entries.length} events</summary>
    <label><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /> Capture section outputs</label>
    <button type="button" onClick={clear}>Clear log</button>
    <p>Local session only · last 30 events. Each completed request shows its block flow below. Outputs are structured results, not private reasoning. Private gs:// references are shown for debugging; raw media and credentials are excluded. These are not public download links.</p>
    <details><summary>Current session state</summary><pre>{JSON.stringify(debugSafe(state), null, 2)}</pre></details>
    {!entries.length && <p>Enable capture, then send a message or upload media.</p>}
    {[...entries].reverse().map((entry, entryIndex) => <details key={entry.id} open={entryIndex === 0}>
      <summary>#{entry.id} {entry.label} · {entry.status} · {entry.elapsed_ms} ms total</summary>
      {entry.output?.evidence_id && <p>Media branches run concurrently: direct bytes → Gemini → classification; independent copy → storage. The response does not wait for storage. Completion appears in a separate storage event.</p>}
      <ol className="debug-flow" aria-label={`Processing flow for ${entry.label}`}>
        {debugBlocks(entry).map((block, index) => <li className={`debug-block ${block.status || ''}`} key={index}>
          <header><b>{index + 1}. {block.stage}</b><small>{block.model || 'Code / no LLM'}{block.elapsed_ms != null ? ` · ${block.elapsed_ms} ms` : ''}</small></header>
          <details open><summary>Output</summary><pre>{JSON.stringify(block.output, null, 2)}</pre></details>
        </li>)}
      </ol>
    </details>)}
  </details>
}
