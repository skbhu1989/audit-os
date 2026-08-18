import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { reconciliation } from '../api/client'
import { Card, Table, RiskBadge, Button, ErrorBanner, inr } from '../components/ui'

export default function Tds() {
  const { currentEngagementId } = useApp()
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [summary, setSummary] = useState(null)

  useEffect(() => { if (currentEngagementId) load() }, [currentEngagementId])
  function load() { reconciliation.tdsExceptions(currentEngagementId).then(setRows).catch((e) => setError(e.message)) }

  async function run() {
    setBusy(true); setError(null)
    try { setSummary(await reconciliation.runTds(currentEngagementId)); load() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>

  return (
    <Card title="TDS Reconciliation" eyebrow="Ledger ↔ Challan ↔ Return" right={<Button onClick={run} disabled={busy}>{busy ? 'Running…' : 'Run Reconciliation'}</Button>}>
      <ErrorBanner message={error} />
      {summary && (
        <div className="text-[12px] font-mono text-slate mb-3">
          {summary.sections_analyzed} section(s) analyzed · {summary.exceptions_found} exception(s) ·
          {' '}total interest exposure {inr(summary.total_interest_exposure)}
        </div>
      )}
      <Table
        columns={[
          { key: 'section', label: 'Section', mono: true },
          { key: 'deducted', label: 'Deducted', align: 'right', mono: true, render: (r) => inr(r.deducted) },
          { key: 'paid', label: 'Paid', align: 'right', mono: true, render: (r) => inr(r.paid) },
          { key: 'risk_level', label: 'Risk', render: (r) => <RiskBadge level={r.risk_level} /> },
          { key: 'reason', label: 'Status', muted: true },
        ]}
        rows={rows}
        emptyText="No TDS exceptions yet — run reconciliation above."
      />
    </Card>
  )
}
