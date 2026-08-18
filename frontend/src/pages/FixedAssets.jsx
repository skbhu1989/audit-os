import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { fixedAssets } from '../api/client'
import { Card, Table, StatBlock, ErrorBanner, inr } from '../components/ui'

export default function FixedAssets() {
  const { currentEngagementId } = useApp()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!currentEngagementId) return
    fixedAssets.get(currentEngagementId).then(setData).catch((e) => setError(e.message))
  }, [currentEngagementId])

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-3.5">
        <StatBlock label="FAR Gross Total" value={inr(data.far_gross_total)} accent="gold" />
        <StatBlock label="GL PPE Balance" value={data.gl_ppe_balance !== null ? inr(data.gl_ppe_balance) : '—'} accent="gold" />
        <StatBlock
          label="FAR ↔ GL"
          value={data.reconciliation_status}
          sub={data.reconciliation_status === 'MISMATCH' ? `Difference: ${inr(data.reconciliation_difference)}` : undefined}
          accent={data.reconciliation_status === 'MATCHED' ? 'green' : data.reconciliation_status === 'NO_DATA' ? 'amber' : 'red'}
        />
      </div>
      <Card title="Fixed Asset Register" eyebrow="Depreciation consistency checked against a straightforward SLM/WDV recalculation">
        <Table
          columns={[
            { key: 'asset_code', label: 'Code', mono: true },
            { key: 'description', label: 'Description' },
            { key: 'category', label: 'Category', muted: true },
            { key: 'gross_block', label: 'Gross Block', align: 'right', mono: true, render: (r) => inr(r.gross_block) },
            { key: 'accum_depreciation', label: 'Accum. Dep.', align: 'right', mono: true, render: (r) => inr(r.accum_depreciation) },
            { key: 'expected_accum_depreciation', label: 'Expected Dep.', align: 'right', mono: true, render: (r) => r.expected_accum_depreciation !== null ? inr(r.expected_accum_depreciation) : '—' },
            { key: 'physically_verified', label: 'Verified', render: (r) => r.physically_verified ? <span className="text-green">✓</span> : <span className="text-faint">Pending</span> },
            { key: 'flag', label: 'Flag', muted: true, render: (r) => r.flag ? <span className="text-amber text-[12px]">{r.flag}</span> : <span className="text-green text-[12px]">—</span> },
          ]}
          rows={data.assets}
          emptyText="No fixed assets uploaded yet — go to Data Centre."
        />
      </Card>
    </div>
  )
}
