import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { analytics, dataApi } from '../api/client'
import { Card, Table, Button, ErrorBanner, inr } from '../components/ui'

export default function TrialBalance() {
  const { currentEngagementId } = useApp()
  const [tb, setTb] = useState([])
  const [suggestions, setSuggestions] = useState([])
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (currentEngagementId) load() }, [currentEngagementId])

  function load() {
    dataApi.trialBalance(currentEngagementId).then(setTb).catch((e) => setError(e.message))
    analytics.mappingSuggestions(currentEngagementId).then(setSuggestions).catch((e) => setError(e.message))
  }

  async function applySuggestions() {
    setBusy(true); setError(null)
    try { await analytics.applySuggestions(currentEngagementId, 0.6); load() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function runFlags() {
    setBusy(true); setError(null)
    try { await analytics.runTbFlags(currentEngagementId); load() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (!currentEngagementId) return <div className="text-faint p-10 text-center">Select an engagement first.</div>

  const totalDr = tb.reduce((s, r) => s + (r.debit || 0), 0)
  const totalCr = tb.reduce((s, r) => s + (r.credit || 0), 0)
  const ties = Math.abs(totalDr - totalCr) < 1

  return (
    <div className="flex flex-col gap-4">
      <ErrorBanner message={error} />
      <Card
        title="Trial Balance"
        eyebrow={ties ? 'TB TIES ✓' : 'TB DOES NOT TIE'}
        right={<div className="flex gap-2">
          <Button variant="outline" onClick={applySuggestions} disabled={busy}>Apply Mapping Suggestions</Button>
          <Button variant="outline" onClick={runFlags} disabled={busy}>Run Balance Flags</Button>
        </div>}
      >
        <Table
          columns={[
            { key: 'ledger_name', label: 'Ledger' },
            { key: 'fs_line', label: 'FS Line', muted: true },
            { key: 'debit', label: 'Debit', align: 'right', mono: true, render: (r) => r.debit ? inr(r.debit) : '—' },
            { key: 'credit', label: 'Credit', align: 'right', mono: true, render: (r) => r.credit ? inr(r.credit) : '—' },
            { key: 'flag', label: 'Flag', render: (r) => r.flag ? <span className="text-red text-[12px]">{r.flag}</span> : <span className="text-green text-[12px]">Clean</span> },
          ]}
          rows={tb}
          emptyText="No trial balance uploaded yet — go to Data Centre."
        />
      </Card>

      <Card title="FS-Line Mapping Suggestions" eyebrow="Human approval required before final (Section O)">
        <Table
          columns={[
            { key: 'ledger_name', label: 'Ledger' },
            { key: 'suggested_fs_line', label: 'Suggested FS Line' },
            { key: 'confidence', label: 'Confidence', align: 'right', mono: true, render: (r) => `${(r.confidence * 100).toFixed(0)}%` },
            { key: 'already_mapped', label: 'Approved?', render: (r) => r.already_mapped ? <span className="text-green">Yes</span> : <span className="text-faint">Pending</span> },
          ]}
          rows={suggestions}
        />
      </Card>
    </div>
  )
}
