import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { loans } from '../api/client'
import { Card, Table, StatBlock, ErrorBanner, inr } from '../components/ui'

export default function Loans() {
  const { currentEngagementId } = useApp()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!currentEngagementId) return
    loans.get(currentEngagementId).then(setData).catch((e) => setError(e.message))
  }, [currentEngagementId])

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-3.5">
        <StatBlock label="Total Borrowings" value={inr(data.borrowings_total)} accent="gold" />
        <StatBlock
          label="Loans ↔ GL"
          value={data.reconciliation_status}
          sub={data.reconciliation_status === 'MISMATCH' ? `Difference: ${inr(data.reconciliation_difference)}` : undefined}
          accent={data.reconciliation_status === 'MATCHED' ? 'green' : data.reconciliation_status === 'NO_DATA' ? 'amber' : 'red'}
        />
        <StatBlock label="Possible Defaults" value={data.overdue_count} accent={data.overdue_count > 0 ? 'red' : 'green'} />
      </div>
      <Card title="Loan Register" eyebrow="CARO clause (ix) — Repayment of Borrowings">
        <Table
          columns={[
            { key: 'lender_or_borrower', label: 'Party' },
            { key: 'direction', label: 'Direction', mono: true },
            { key: 'outstanding_balance', label: 'Outstanding', align: 'right', mono: true, render: (r) => inr(r.outstanding_balance) },
            { key: 'maturity_date', label: 'Maturity', mono: true, render: (r) => r.maturity_date || '—' },
            { key: 'default_flag', label: 'Default Flag', render: (r) => r.default_flag ? <span className="text-red text-[12px]">{r.default_flag}</span> : <span className="text-green text-[12px]">—</span> },
            { key: 'interest_flag', label: 'Interest Flag', muted: true, render: (r) => r.interest_flag || '—' },
          ]}
          rows={data.loans}
          emptyText="No loans uploaded yet — go to Data Centre."
        />
      </Card>
    </div>
  )
}
