import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { risk, analytics } from '../api/client'
import { Card, RiskBadge, Button, ErrorBanner } from '../components/ui'

export default function Risk() {
  const { currentEngagementId } = useApp()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (currentEngagementId) load() }, [currentEngagementId])
  function load() { risk.dashboard(currentEngagementId).then(setData).catch((e) => setError(e.message)) }

  async function runJournalRisk() {
    setBusy(true); setError(null)
    try { await analytics.runJournalRisk(currentEngagementId); load() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>
  if (!data) return <ErrorBanner message={error} />

  return (
    <Card
      title="Multi-Category Audit Risk"
      eyebrow={`${data.scored_count} scored · ${data.insufficient_data_count} no data yet · highest: ${data.highest_risk_category || '—'}`}
      right={<Button onClick={runJournalRisk} disabled={busy}>{busy ? 'Scoring…' : 'Run Journal Risk Scoring'}</Button>}
    >
      <ErrorBanner message={error} />
      <div className="grid grid-cols-3 gap-3">
        {data.categories.map((c) => (
          <div key={c.category} className="border border-paper-line rounded p-3 flex flex-col gap-1">
            <div className="flex justify-between items-center">
              <span className="text-[13px] font-medium">{c.category}</span>
              <RiskBadge level={c.status === 'SCORED' ? c.level : 'NO_DATA'} />
            </div>
            {c.status === 'SCORED' ? (
              <>
                <div className="font-mono text-[20px] text-ink">{c.score}<span className="text-[11px] text-faint">/100</span></div>
                <ul className="text-[11px] text-slate">
                  {c.factors.map((f, i) => <li key={i}>• {f}</li>)}
                </ul>
              </>
            ) : (
              <div className="text-[11px] text-faint italic">{c.data_gap_reason}</div>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}
