import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { monthEndClose } from '../api/client'
import { Card, Table, RiskBadge, Button, ErrorBanner } from '../components/ui'

const STATUS_LEVEL = { COMPLETE: 'GREEN', REVIEW_REQUIRED: 'AMBER', IN_PROGRESS: 'AMBER', NOT_STARTED: 'RED', NOT_APPLICABLE: 'NO_DATA' }

export default function MonthEndClose() {
  const { currentEngagementId } = useApp()
  const [period, setPeriod] = useState('Mar-2026')
  const [tasks, setTasks] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (currentEngagementId) load() }, [currentEngagementId])

  function load() {
    monthEndClose.get(currentEngagementId, period).then(setTasks).catch(() => setTasks([]))
  }

  async function init() {
    setBusy(true); setError(null)
    try { await monthEndClose.init(currentEngagementId, period); load() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>

  const progress = tasks && tasks.length ? Math.round(100 * tasks.filter((t) => t.status === 'COMPLETE').length / tasks.length) : 0

  return (
    <Card
      title={`Month-End Close — ${period}`}
      eyebrow={tasks ? `${progress}% complete` : ''}
      right={
        <div className="flex gap-2 items-center">
          <input value={period} onChange={(e) => setPeriod(e.target.value)} className="border border-paper-line rounded px-2 py-1 text-[12px] font-mono w-28" />
          <Button onClick={init} disabled={busy}>{busy ? 'Loading…' : 'Init / Refresh'}</Button>
        </div>
      }
    >
      <ErrorBanner message={error} />
      <Table
        columns={[
          { key: 'category', label: 'Category', mono: true },
          { key: 'task_name', label: 'Task' },
          { key: 'is_system_computed', label: 'Source', render: (r) => r.is_system_computed ? <span className="text-green text-[11px]">System</span> : <span className="text-faint text-[11px]">Manual</span> },
          { key: 'status', label: 'Status', render: (r) => <RiskBadge level={STATUS_LEVEL[r.status]} /> },
          { key: 'evidence_note', label: 'Note', muted: true },
        ]}
        rows={tasks || []}
        emptyText="No close checklist yet for this period — click Init / Refresh."
      />
    </Card>
  )
}
