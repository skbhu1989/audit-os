import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { workingPapers } from '../api/client'
import { Card, Table, Button, ErrorBanner } from '../components/ui'

export default function WorkingPapers() {
  const { currentEngagementId } = useApp()
  const [rows, setRows] = useState([])
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (currentEngagementId) load() }, [currentEngagementId])
  function load() { workingPapers.list(currentEngagementId).then(setRows).catch((e) => setError(e.message)) }

  async function draft(fn) {
    setBusy(true); setError(null)
    try { await fn(currentEngagementId); load() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function transition(wp, action) {
    setBusy(true); setError(null)
    try {
      if (action === 'prepare') await workingPapers.prepare(currentEngagementId, wp.id)
      else if (action === 'review') await workingPapers.review(currentEngagementId, wp.id)
      else if (action === 'approve') await workingPapers.approve(currentEngagementId, wp.id)
      load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>

  return (
    <Card
      title="Working Papers"
      eyebrow="Auto-drafted, human sign-off required"
      right={
        <div className="flex gap-2">
          <Button variant="outline" disabled={busy} onClick={() => draft(workingPapers.autoDraftGst)}>+ GST</Button>
          <Button variant="outline" disabled={busy} onClick={() => draft(workingPapers.autoDraftTds)}>+ TDS</Button>
          <Button variant="outline" disabled={busy} onClick={() => draft(workingPapers.autoDraftJournalTesting)}>+ JE Testing</Button>
        </div>
      }
    >
      <ErrorBanner message={error} />
      <Table
        columns={[
          { key: 'wp_code', label: 'Code', mono: true },
          { key: 'objective', label: 'Objective', muted: true },
          { key: 'status', label: 'Status', mono: true },
          {
            key: 'action', label: '', align: 'right',
            render: (r) => (
              <div className="flex gap-1.5 justify-end">
                {r.status === 'DRAFT' && <Button variant="outline" onClick={() => transition(r, 'prepare')}>Prepare</Button>}
                {r.status === 'PREPARED' && <Button variant="outline" onClick={() => transition(r, 'review')}>Review</Button>}
                {r.status === 'REVIEWED' && <Button onClick={() => transition(r, 'approve')}>Approve</Button>}
                {r.status === 'APPROVED' && <span className="text-green text-[12px] font-mono">✓ Approved</span>}
              </div>
            ),
          },
        ]}
        rows={rows}
        emptyText="No working papers yet — draft one above."
      />
    </Card>
  )
}
