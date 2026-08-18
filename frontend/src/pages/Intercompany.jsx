import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { intercompany } from '../api/client'
import { Card, Table, StatBlock, RiskBadge, ErrorBanner, inr } from '../components/ui'

const STATUS_LEVEL = { MATCHED: 'GREEN', MISMATCHED: 'AMBER', MISSING_IN_BOOKS: 'RED', MISSING_IN_CONFIRMATION: 'RED' }

export default function Intercompany() {
  const { currentEngagementId } = useApp()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!currentEngagementId) return
    intercompany.get(currentEngagementId).then(setData).catch((e) => setError(e.message))
  }, [currentEngagementId])

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3.5">
        <StatBlock label="Matched" value={data.matched_count} accent="green" />
        <StatBlock label="Unresolved" value={data.unresolved_count} accent={data.unresolved_count > 0 ? 'red' : 'green'} />
      </div>

      <Card title="Counterparty Net Position" eyebrow="From this entity's own books (positive = counterparty owes us)">
        <Table
          columns={[
            { key: 'counterparty_name', label: 'Counterparty' },
            { key: 'net_books_position', label: 'Net Position', align: 'right', mono: true, render: (r) => inr(r.net_books_position) },
            { key: 'transaction_count', label: 'Transactions', align: 'right', mono: true },
          ]}
          rows={data.counterparty_summary}
          emptyText="No intercompany ledger uploaded yet."
        />
      </Card>

      <Card title="Books ↔ Confirmation Reconciliation" eyebrow="Section 33 — internal ledger vs counterparty confirmation">
        <Table
          columns={[
            { key: 'counterparty_name', label: 'Counterparty' },
            { key: 'status', label: 'Status', render: (r) => <RiskBadge level={STATUS_LEVEL[r.status] || 'NO_DATA'} /> },
            { key: 'books_amount', label: 'Books', align: 'right', mono: true, render: (r) => r.books_amount !== null ? inr(r.books_amount) : '—' },
            { key: 'confirmation_amount', label: 'Confirmation', align: 'right', mono: true, render: (r) => r.confirmation_amount !== null ? inr(r.confirmation_amount) : '—' },
            { key: 'difference', label: 'Difference', align: 'right', mono: true, render: (r) => r.difference !== null ? inr(r.difference) : '—' },
            { key: 'likely_cause', label: 'Likely Cause', muted: true },
          ]}
          rows={data.matches}
          emptyText="No intercompany data uploaded yet — go to Data Centre."
        />
      </Card>
    </div>
  )
}
