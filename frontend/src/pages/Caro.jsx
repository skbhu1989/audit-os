import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { caro as caroApi } from '../api/client'
import { Card, Table, RiskBadge, Button, ErrorBanner } from '../components/ui'

const DATA_LEVEL = { DATA_BACKED: 'GREEN', INSUFFICIENT_DATA: 'NO_DATA' }

export default function Caro() {
  const { currentEngagementId } = useApp()
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (currentEngagementId) load() }, [currentEngagementId])
  function load() { caroApi.list(currentEngagementId).then(setRows).catch(() => setRows([])) }

  async function init() {
    setBusy(true); setError(null)
    try { await caroApi.init(currentEngagementId); load() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function transition(clause, action) {
    setBusy(true); setError(null)
    try {
      if (action === 'prepare') await caroApi.prepare(currentEngagementId, clause.clause_no)
      else if (action === 'review') await caroApi.review(currentEngagementId, clause.clause_no)
      else if (action === 'approve') {
        const text = window.prompt('Final clause response:', clause.draft_response || '')
        if (text === null) return
        await caroApi.approve(currentEngagementId, clause.clause_no, text)
      }
      load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>

  return (
    <Card title="CARO 2020 Clauses" eyebrow="System never auto-issues the final conclusion" right={<Button onClick={init} disabled={busy}>{busy ? '…' : 'Init / Refresh'}</Button>}>
      <ErrorBanner message={error} />
      <Table
        columns={[
          { key: 'clause_no', label: 'Clause', mono: true },
          { key: 'title', label: 'Title' },
          { key: 'data_status', label: 'Data', render: (r) => <RiskBadge level={DATA_LEVEL[r.data_status]} /> },
          { key: 'status', label: 'Sign-off', mono: true },
          {
            key: 'action', label: '', align: 'right',
            render: (r) => (
              <div className="flex gap-1.5 justify-end">
                {(r.status === 'NOT_STARTED' || r.status === 'DRAFT') && <Button variant="outline" onClick={() => transition(r, 'prepare')}>Prepare</Button>}
                {r.status === 'PREPARED' && <Button variant="outline" onClick={() => transition(r, 'review')}>Review</Button>}
                {r.status === 'REVIEWED' && <Button onClick={() => transition(r, 'approve')}>Approve</Button>}
                {r.status === 'APPROVED' && <span className="text-green text-[12px] font-mono">✓</span>}
              </div>
            ),
          },
        ]}
        rows={rows || []}
        emptyText="Click Init / Refresh to seed the 21 CARO clauses."
      />
    </Card>
  )
}
