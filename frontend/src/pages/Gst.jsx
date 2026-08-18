import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { reconciliation } from '../api/client'
import { Card, Table, RiskBadge, Button, ErrorBanner, inr } from '../components/ui'

export default function Gst() {
  const { currentEngagementId } = useApp()
  const [exceptionsList, setExceptionsList] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [summary, setSummary] = useState(null)

  useEffect(() => { if (currentEngagementId) load() }, [currentEngagementId])

  function load() {
    reconciliation.gstExceptions(currentEngagementId).then(setExceptionsList).catch((e) => setError(e.message))
  }

  async function run() {
    setBusy(true); setError(null)
    try {
      const res = await reconciliation.runGst(currentEngagementId)
      setSummary(res)
      load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>

  return (
    <div className="flex flex-col gap-4">
      <Card title="GST Reconciliation" eyebrow="Books ↔ GSTR-1 ↔ GSTR-3B ↔ GSTR-2B" right={<Button onClick={run} disabled={busy}>{busy ? 'Running…' : 'Run Reconciliation'}</Button>}>
        <ErrorBanner message={error} />
        {summary && (
          <div className="text-[12px] font-mono text-slate mb-3">
            Books vs GSTR-1: {summary.books_vs_gstr1.matched}/{summary.books_vs_gstr1.total} matched ·
            {' '}Purchase vs GSTR-2B: {summary.purchase_vs_gstr2b.matched}/{summary.purchase_vs_gstr2b.total} matched ·
            {' '}{summary.gstr1_vs_gstr3b_periods_flagged} period(s) flagged
          </div>
        )}
        <Table
          columns={[
            { key: 'recon_type', label: 'Type', mono: true },
            { key: 'period', label: 'Period' },
            { key: 'document_no', label: 'Doc No' },
            { key: 'party_name', label: 'Party' },
            { key: 'difference', label: 'Difference', align: 'right', mono: true, render: (r) => inr(r.difference) },
            { key: 'risk_level', label: 'Risk', render: (r) => <RiskBadge level={r.risk_level} /> },
            { key: 'reason', label: 'Reason', muted: true },
          ]}
          rows={exceptionsList}
          emptyText="No GST exceptions yet — run reconciliation above."
        />
      </Card>
    </div>
  )
}
