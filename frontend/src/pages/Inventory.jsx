import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { inventory } from '../api/client'
import { Card, Table, StatBlock, RiskBadge, ErrorBanner, inr } from '../components/ui'

export default function Inventory() {
  const { currentEngagementId } = useApp()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!currentEngagementId) return
    inventory.get(currentEngagementId).then(setData).catch((e) => setError(e.message))
  }, [currentEngagementId])

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-4 gap-3.5">
        <StatBlock label="Inventory Cost Total" value={inr(data.inventory_cost_total)} accent="gold" />
        <StatBlock label="Write-down Required" value={inr(data.total_write_down_required)} accent={data.total_write_down_required > 0 ? 'red' : 'green'} />
        <StatBlock label="Slow-moving Items" value={data.slow_moving_count} accent="amber" />
        <StatBlock label="Obsolete Items" value={data.obsolete_count} accent="red" />
      </div>
      <Card title="Inventory Register" eyebrow={`Inventory ↔ GL: ${data.reconciliation_status}${data.reconciliation_status === 'MISMATCH' ? ` (diff ${inr(data.reconciliation_difference)})` : ''}`}>
        <Table
          columns={[
            { key: 'item_code', label: 'Code', mono: true },
            { key: 'description', label: 'Description' },
            { key: 'quantity_on_hand', label: 'Qty', align: 'right', mono: true },
            { key: 'cost_value', label: 'Cost Value', align: 'right', mono: true, render: (r) => r.cost_value !== null ? inr(r.cost_value) : '—' },
            { key: 'nrv_value', label: 'NRV', align: 'right', mono: true, render: (r) => r.nrv_value !== null ? inr(r.nrv_value) : '—' },
            { key: 'write_down_required', label: 'Write-down', align: 'right', mono: true, render: (r) => r.write_down_required ? <span className="text-red">{inr(r.write_down_required)}</span> : '—' },
            { key: 'ageing_category', label: 'Ageing', render: (r) => <RiskBadge level={r.ageing_category === 'OBSOLETE' ? 'HIGH' : r.ageing_category === 'SLOW_MOVING' ? 'MEDIUM' : r.ageing_category === 'UNKNOWN' ? 'NO_DATA' : 'LOW'} /> },
          ]}
          rows={data.items}
          emptyText="No inventory uploaded yet — go to Data Centre."
        />
      </Card>
    </div>
  )
}
