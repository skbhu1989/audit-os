import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { investments } from '../api/client'
import { Card, Table, StatBlock, ErrorBanner, inr } from '../components/ui'

export default function Investments() {
  const { currentEngagementId } = useApp()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!currentEngagementId) return
    investments.get(currentEngagementId).then(setData).catch((e) => setError(e.message))
  }, [currentEngagementId])

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-3.5">
        <StatBlock label="Cost Total" value={inr(data.cost_total)} accent="gold" />
        <StatBlock
          label="Investments ↔ GL"
          value={data.reconciliation_status}
          sub={data.reconciliation_status === 'MISMATCH' ? `Difference: ${inr(data.reconciliation_difference)}` : undefined}
          accent={data.reconciliation_status === 'MATCHED' ? 'green' : data.reconciliation_status === 'NO_DATA' ? 'amber' : 'red'}
        />
        <StatBlock label="Flagged" value={data.flagged_count} accent={data.flagged_count > 0 ? 'amber' : 'green'} />
      </div>
      <Card title="Investment Register" eyebrow="Fair value staleness + impairment indicator (Ind AS 109 consideration, not a conclusion)">
        <Table
          columns={[
            { key: 'investee_name', label: 'Investee' },
            { key: 'cost', label: 'Cost', align: 'right', mono: true, render: (r) => inr(r.cost) },
            { key: 'fair_value', label: 'Fair Value', align: 'right', mono: true, render: (r) => r.fair_value !== null ? inr(r.fair_value) : '—' },
            {
              key: 'unrealized_gain_loss', label: 'Gain/(Loss)', align: 'right', mono: true,
              render: (r) => r.unrealized_gain_loss !== null
                ? <span className={r.unrealized_gain_loss < 0 ? 'text-red' : 'text-green'}>{inr(r.unrealized_gain_loss)}</span>
                : '—',
            },
            { key: 'flags', label: 'Flags', muted: true, render: (r) => r.flags.length ? r.flags.join('; ') : '—' },
          ]}
          rows={data.investments}
          emptyText="No investments uploaded yet — go to Data Centre."
        />
      </Card>
    </div>
  )
}
