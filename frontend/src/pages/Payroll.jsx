import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { reconciliation } from '../api/client'
import { Card, Table, RiskBadge, Button, ErrorBanner, inr } from '../components/ui'

export default function Payroll() {
  const { currentEngagementId } = useApp()
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => { if (currentEngagementId) load() }, [currentEngagementId])
  function load() { reconciliation.payrollExceptions(currentEngagementId).then(setRows).catch((e) => setError(e.message)) }

  async function run() {
    setBusy(true); setError(null)
    try { await reconciliation.runPayroll(currentEngagementId); load() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>

  return (
    <Card title="PF / ESI / PT Reconciliation" eyebrow="Payroll Liability ↔ Challan" right={<Button onClick={run} disabled={busy}>{busy ? 'Running…' : 'Run Reconciliation'}</Button>}>
      <ErrorBanner message={error} />
      <Table
        columns={[
          { key: 'scheme', label: 'Scheme', mono: true },
          { key: 'period', label: 'Period' },
          { key: 'liability', label: 'Liability', align: 'right', mono: true, render: (r) => inr(r.liability) },
          { key: 'paid', label: 'Paid', align: 'right', mono: true, render: (r) => inr(r.paid) },
          { key: 'risk_level', label: 'Risk', render: (r) => <RiskBadge level={r.risk_level} /> },
          { key: 'reason', label: 'Status', muted: true },
        ]}
        rows={rows}
        emptyText="No payroll exceptions yet — run reconciliation above."
      />
    </Card>
  )
}
