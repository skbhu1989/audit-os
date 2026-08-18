import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { reconciliation } from '../api/client'
import { Card, Table, RiskBadge, ErrorBanner, inr } from '../components/ui'

export default function Bank() {
  const { currentEngagementId } = useApp()
  const [bankRows, setBankRows] = useState([])
  const [scheme, setScheme] = useState('TDS')
  const [challanRows, setChallanRows] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!currentEngagementId) return
    reconciliation.bankReconciliation(currentEngagementId).then(setBankRows).catch((e) => setError(e.message))
  }, [currentEngagementId])

  useEffect(() => {
    if (!currentEngagementId) return
    reconciliation.challanMapping(currentEngagementId, scheme).then(setChallanRows).catch((e) => setError(e.message))
  }, [currentEngagementId, scheme])

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>

  return (
    <div className="flex flex-col gap-4">
      <ErrorBanner message={error} />
      <Card title="Bank Reconciliation" eyebrow="Bank Statement ↔ GL Cash/Bank Ledger">
        <Table
          columns={[
            { key: 'status', label: 'Status', render: (r) => <RiskBadge level={r.status === 'MATCHED' ? 'GREEN' : 'AMBER'} /> },
            { key: 'description', label: 'Description', muted: true },
            { key: 'bank_amount', label: 'Bank Amount', align: 'right', mono: true, render: (r) => r.bank_amount !== null ? inr(r.bank_amount) : '—' },
            { key: 'ledger_amount', label: 'Ledger Amount', align: 'right', mono: true, render: (r) => r.ledger_amount !== null ? inr(r.ledger_amount) : '—' },
          ]}
          rows={bankRows}
          emptyText="No bank statement or GL bank ledger data yet."
        />
      </Card>

      <Card
        title="Challan Mapping"
        eyebrow="Confirms a statutory challan actually appears in the bank statement"
        right={
          <select value={scheme} onChange={(e) => setScheme(e.target.value)} className="border border-paper-line rounded px-2 py-1 text-[12px] font-mono">
            {['GST', 'TDS', 'PF', 'ESI', 'PT'].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        }
      >
        <Table
          columns={[
            { key: 'tax_head', label: 'Section/Head', mono: true },
            { key: 'amount', label: 'Amount', align: 'right', mono: true, render: (r) => inr(r.amount) },
            { key: 'status', label: 'Status', render: (r) => <RiskBadge level={r.status === 'MATCHED' ? 'GREEN' : r.status === 'MISMATCHED' ? 'AMBER' : 'RED'} /> },
            { key: 'matched_amount', label: 'Bank Amount', align: 'right', mono: true, render: (r) => r.matched_amount !== null ? inr(r.matched_amount) : '—' },
          ]}
          rows={challanRows}
          emptyText={`No ${scheme} challans uploaded yet.`}
        />
      </Card>
    </div>
  )
}
