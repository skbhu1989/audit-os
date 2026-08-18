import { useState } from 'react'
import { useApp } from '../context/AppContext'
import { aiAssistant } from '../api/client'
import { Card, Button, ErrorBanner } from '../components/ui'

const PROMPTS = [
  'Find duplicate vendors',
  'Show journal entries posted at year end',
  'Reconcile GST turnover with revenue',
  'Check whether TDS has been deducted correctly',
  'Is the trial balance status ok, does it tie?',
]

export default function AiAssistant() {
  const { currentEngagementId } = useApp()
  const [question, setQuestion] = useState('')
  const [log, setLog] = useState([])
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function ask(q) {
    const text = q ?? question
    if (!text.trim()) return
    setBusy(true); setError(null)
    try {
      const res = await aiAssistant.ask(currentEngagementId, text)
      setLog((l) => [res, ...l])
      setQuestion('')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>

  return (
    <Card title="AI Audit Assistant" eyebrow="Deterministic — every answer traces to real data, no LLM call in this build">
      <ErrorBanner message={error} />
      <div className="flex gap-1.5 flex-wrap mb-3">
        {PROMPTS.map((p) => (
          <button key={p} onClick={() => ask(p)} disabled={busy}
            className="text-[12px] px-2.5 py-1 rounded-full border border-gold text-gold bg-gold-soft hover:bg-gold/10">
            {p}
          </button>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={question} onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && ask()}
          placeholder="Ask a question about this engagement's data…"
          className="flex-1 border border-paper-line rounded px-3 py-2 text-[13px]"
        />
        <Button onClick={() => ask()} disabled={busy}>{busy ? '…' : 'Ask'}</Button>
      </div>

      <div className="flex flex-col gap-3 mt-4">
        {log.map((entry, i) => (
          <div key={i} className="border border-paper-line rounded p-3.5 bg-paper">
            <div className="font-serif italic text-[14px] mb-2">"{entry.question}"</div>
            <div className="flex flex-col gap-1.5 text-[12.5px]">
              <Field label="ANSWER" value={entry.answer} strong />
              <Field label="DATA USED" value={entry.data_used} mono />
              <Field label="CALCULATION" value={entry.calculation} />
              <Field label="SOURCE" value={entry.source} />
              <Field label="STANDARD" value={entry.standard} />
              <Field label="EVIDENCE" value={entry.evidence} />
              <Field label="IMPLICATION" value={entry.implication} />
              <Field label="PROCEDURE" value={entry.procedure} />
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function Field({ label, value, strong, mono }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-2">
      <div className="font-mono text-[10px] tracking-[0.06em] text-gold uppercase pt-0.5">{label}</div>
      <div className={`${strong ? 'font-medium text-ink' : 'text-slate'} ${mono ? 'font-mono text-[11px]' : ''}`}>{value}</div>
    </div>
  )
}
