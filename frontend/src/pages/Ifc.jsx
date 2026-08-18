import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { ifc as ifcApi } from '../api/client'
import { Card, Table, RiskBadge, Button, ErrorBanner } from '../components/ui'

export default function Ifc() {
  const { currentEngagementId } = useApp()
  const [rows, setRows] = useState([])
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (currentEngagementId) load() }, [currentEngagementId])
  function load() { ifcApi.list(currentEngagementId).then(setRows).catch((e) => setError(e.message)) }

  async function run() {
    setBusy(true); setError(null)
    try { await ifcApi.runAutomated(currentEngagementId); load() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function recordManual(control, result) {
    try { await ifcApi.recordManual(currentEngagementId, control.control_id, { test_result: result }); load() }
    catch (e) { setError(e.message) }
  }

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>

  return (
    <Card title="Internal Financial Controls" eyebrow="P2P / O2C / R2R / Treasury / Tax" right={<Button onClick={run} disabled={busy}>{busy ? 'Running…' : 'Run Automated Tests'}</Button>}>
      <ErrorBanner message={error} />
      <Table
        columns={[
          { key: 'process', label: 'Process', mono: true },
          { key: 'control_description', label: 'Control', muted: true },
          { key: 'automatable', label: 'Type', render: (r) => r.automatable ? <span className="text-green text-[11px]">Automated</span> : <span className="text-faint text-[11px]">Manual</span> },
          {
            key: 'test_result', label: 'Result',
            render: (r) => r.test_result
              ? <RiskBadge level={r.test_result === 'EFFECTIVE' ? 'GREEN' : 'RED'} />
              : (
                <div className="flex gap-1">
                  <button onClick={() => recordManual(r, 'EFFECTIVE')} className="text-[11px] text-green border border-green/40 rounded px-1.5">Effective</button>
                  <button onClick={() => recordManual(r, 'EXCEPTION_NOTED')} className="text-[11px] text-red border border-red/40 rounded px-1.5">Exception</button>
                </div>
              ),
          },
          { key: 'exception_detail', label: 'Detail', muted: true },
        ]}
        rows={rows}
        emptyText="Click Run Automated Tests to seed and test the control library."
      />
    </Card>
  )
}
