import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { exceptions as excApi } from '../api/client'
import { Card, Table, RiskBadge, Button, ErrorBanner, inr } from '../components/ui'

export default function Exceptions() {
  const { currentEngagementId } = useApp()
  const [rows, setRows] = useState([])
  const [filterModule, setFilterModule] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState(null)
  const [rootCause, setRootCause] = useState(null)
  const [queryDraft, setQueryDraft] = useState(null)

  useEffect(() => { if (currentEngagementId) load() }, [currentEngagementId, filterModule])

  function load() {
    excApi.list(currentEngagementId, filterModule ? { module: filterModule } : undefined)
      .then(setRows).catch((e) => setError(e.message))
  }

  async function sync() {
    setBusy(true); setError(null)
    try { await excApi.sync(currentEngagementId); load() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function openExplain(exc) {
    setSelected(exc)
    setRootCause(null)
    setQueryDraft(null)
    try { setRootCause(await excApi.rootCause(currentEngagementId, exc.id)) }
    catch (e) { setError(e.message) }
  }

  async function draftQuery() {
    try { setQueryDraft(await excApi.draftQuery(currentEngagementId, selected.id)); load() }
    catch (e) { setError(e.message) }
  }

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>

  return (
    <div className="flex gap-4">
      <div className="flex-1 min-w-0">
        <Card
          title="Exception Register"
          eyebrow="Section 60 — Central hub"
          right={
            <div className="flex gap-2 items-center">
              <select value={filterModule} onChange={(e) => setFilterModule(e.target.value)} className="border border-paper-line rounded px-2 py-1 text-[12px] font-mono">
                <option value="">All modules</option>
                {['GST', 'TDS', 'PF', 'ESI', 'PT', 'AP', 'AR'].map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <Button onClick={sync} disabled={busy}>{busy ? 'Syncing…' : 'Sync from AP/AR/Challans'}</Button>
            </div>
          }
        >
          <ErrorBanner message={error} />
          <Table
            columns={[
              { key: 'module', label: 'Module', mono: true },
              { key: 'reason', label: 'Reason', muted: true },
              { key: 'amount', label: 'Amount', align: 'right', mono: true, render: (r) => inr(r.amount || r.difference) },
              { key: 'risk_level', label: 'Risk', render: (r) => <RiskBadge level={r.risk_level} /> },
              { key: 'status', label: 'Status', mono: true },
              {
                key: 'action', label: '', align: 'right',
                render: (r) => <Button variant="outline" onClick={() => openExplain(r)}>Explain</Button>,
              },
            ]}
            rows={rows}
            emptyText="No exceptions yet — run reconciliation modules, then Sync."
          />
        </Card>
      </div>

      {selected && (
        <div className="w-[380px] shrink-0">
          <Card title="Exception Detail" eyebrow={selected.module} right={<button onClick={() => setSelected(null)} className="text-faint">✕</button>}>
            <div className="text-[13px] text-slate mb-3">{selected.reason}</div>
            {rootCause ? (
              <div className="flex flex-col gap-2 text-[12.5px]">
                <Row label="ROOT CAUSE" value={rootCause.root_cause} strong />
                <Row label="WHAT" value={rootCause.what} />
                <Row label="WHY" value={rootCause.why} />
                <Row label="IMPACT" value={rootCause.impact} />
                <Row label="ACTION" value={rootCause.action} />
              </div>
            ) : <div className="text-faint text-[12px]">Loading root cause…</div>}

            <div className="mt-4 pt-3 border-t border-paper-line">
              {queryDraft ? (
                <div className="text-[12px] bg-paper p-3 rounded border border-paper-line whitespace-pre-wrap">
                  <div className="font-mono text-[10px] text-gold mb-1">DRAFTED — review before sending</div>
                  {queryDraft.query_text}
                </div>
              ) : (
                <Button onClick={draftQuery}>Draft Client Query</Button>
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}

function Row({ label, value, strong }) {
  return (
    <div>
      <div className="font-mono text-[10px] tracking-[0.06em] text-gold uppercase">{label}</div>
      <div className={strong ? 'font-medium text-ink' : 'text-slate'}>{value}</div>
    </div>
  )
}
