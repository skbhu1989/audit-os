import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { apAr } from '../api/client'
import { Card, Table, RiskBadge, ErrorBanner, inr } from '../components/ui'

export default function ApAr() {
  const { currentEngagementId } = useApp()
  const [apAgeing, setApAgeing] = useState([])
  const [arAgeing, setArAgeing] = useState([])
  const [dups, setDups] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!currentEngagementId) return
    apAr.apAgeing(currentEngagementId).then(setApAgeing).catch((e) => setError(e.message))
    apAr.arAgeing(currentEngagementId).then(setArAgeing).catch((e) => setError(e.message))
    apAr.duplicateInvoices(currentEngagementId).then(setDups).catch((e) => setError(e.message))
  }, [currentEngagementId])

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>

  const ageingCols = [
    { key: 'party', label: 'Party' },
    { key: 'invoice_no', label: 'Invoice', mono: true },
    { key: 'outstanding', label: 'Outstanding', align: 'right', mono: true, render: (r) => inr(r.outstanding) },
    { key: 'age_days', label: 'Age (days)', align: 'right', mono: true },
    { key: 'bucket', label: 'Bucket', render: (r) => <RiskBadge level={r.bucket === '>365' ? 'HIGH' : r.bucket === '181-365' ? 'MEDIUM' : 'LOW'} /> },
  ]

  return (
    <div className="flex flex-col gap-4">
      <ErrorBanner message={error} />
      <Card title="AP Ageing" eyebrow="Unpaid balances — settled invoices excluded via real bank payment matching">
        <Table columns={ageingCols} rows={apAgeing} emptyText="No outstanding AP balances." />
      </Card>
      <Card title="AR Ageing" eyebrow="Uncollected balances">
        <Table columns={ageingCols} rows={arAgeing} emptyText="No outstanding AR balances." />
      </Card>
      <Card title="Possible Duplicate Invoices" eyebrow="Same party + amount within 60 days">
        <Table
          columns={[
            { key: 'invoice_a', label: 'Invoice A', mono: true },
            { key: 'invoice_b', label: 'Invoice B', mono: true },
            { key: 'party', label: 'Party' },
            { key: 'amount', label: 'Amount', align: 'right', mono: true, render: (r) => inr(r.amount) },
            { key: 'confidence', label: 'Confidence', render: (r) => <RiskBadge level={r.confidence === 'HIGH' ? 'HIGH' : 'MEDIUM'} /> },
          ]}
          rows={dups}
          emptyText="No possible duplicate invoices identified."
        />
      </Card>
    </div>
  )
}
