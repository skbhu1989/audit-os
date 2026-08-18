import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'
import { clients, engagements as engagementsApi } from '../api/client'
import { Card, Button, Spinner, ErrorBanner, Table } from '../components/ui'

export default function Engagements() {
  const { setCurrentClientId, setCurrentEngagementId } = useApp()
  const navigate = useNavigate()
  const [clientList, setClientList] = useState(null)
  const [engagementsByClient, setEngagementsByClient] = useState({})
  const [error, setError] = useState(null)
  const [showNewClient, setShowNewClient] = useState(false)

  useEffect(() => { load() }, [])

  async function load() {
    try {
      const cs = await clients.list()
      setClientList(cs)
      const map = {}
      for (const c of cs) {
        map[c.id] = await engagementsApi.list(c.id)
      }
      setEngagementsByClient(map)
    } catch (err) {
      setError(err.message)
    }
  }

  function selectEngagement(clientId, engagementId) {
    setCurrentClientId(clientId)
    setCurrentEngagementId(engagementId)
    navigate('/dashboard')
  }

  if (!clientList) return <div className="p-10"><Spinner /></div>

  return (
    <div className="min-h-screen bg-paper p-10">
      <div className="max-w-4xl mx-auto">
        <div className="font-mono text-[10px] tracking-[0.18em] text-gold mb-1">AUDIT OPERATING SYSTEM</div>
        <div className="font-serif text-[26px] text-ink mb-6">Select an engagement</div>
        <ErrorBanner message={error} />

        {clientList.length === 0 ? (
          <Card title="No clients yet">
            <p className="text-[13px] text-slate mb-3">Create your first client to get started.</p>
            <NewClientForm onCreated={load} />
          </Card>
        ) : (
          <div className="flex flex-col gap-4">
            {clientList.map((c) => (
              <Card key={c.id} title={c.legal_name} eyebrow={c.framework || 'Framework not set'}>
                <Table
                  columns={[
                    { key: 'financial_year', label: 'FY' },
                    { key: 'status', label: 'Status' },
                    {
                      key: 'action', label: '', align: 'right',
                      render: (r) => (
                        <Button variant="outline" onClick={() => selectEngagement(c.id, r.id)}>Open</Button>
                      ),
                    },
                  ]}
                  rows={engagementsByClient[c.id] || []}
                  emptyText="No engagements yet for this client."
                />
                <NewEngagementForm clientId={c.id} onCreated={load} />
              </Card>
            ))}
          </div>
        )}

        <div className="mt-6">
          <Button variant="ghost" onClick={() => setShowNewClient((s) => !s)}>
            {showNewClient ? 'Cancel' : '+ Add another client'}
          </Button>
          {showNewClient && (
            <div className="mt-3">
              <Card title="New client">
                <NewClientForm onCreated={() => { load(); setShowNewClient(false) }} />
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function NewClientForm({ onCreated }) {
  const [legalName, setLegalName] = useState('')
  const [framework, setFramework] = useState('IND_AS')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await clients.create({ legal_name: legalName, framework, listing_status: 'UNLISTED' })
      setLegalName('')
      onCreated()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex gap-2 items-end mt-2">
      <div className="flex-1">
        <ErrorBanner message={error} />
        <input required placeholder="Legal name" value={legalName} onChange={(e) => setLegalName(e.target.value)}
          className="border border-paper-line rounded px-3 py-2 text-[13px] w-full" />
      </div>
      <select value={framework} onChange={(e) => setFramework(e.target.value)}
        className="border border-paper-line rounded px-3 py-2 text-[13px]">
        <option value="IND_AS">Ind AS</option>
        <option value="AS">AS</option>
        <option value="IFRS">IFRS</option>
        <option value="OTHER">Other</option>
      </select>
      <Button type="submit" disabled={busy}>Create client</Button>
    </form>
  )
}

function NewEngagementForm({ clientId, onCreated }) {
  const [fy, setFy] = useState('')
  const [reportingDate, setReportingDate] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await engagementsApi.create({
        client_id: clientId, financial_year: fy, reporting_date: reportingDate, framework: 'IND_AS',
      })
      setFy(''); setReportingDate('')
      onCreated()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex gap-2 items-end mt-3 pt-3 border-t border-paper-line">
      <ErrorBanner message={error} />
      <input required placeholder="FY e.g. 2025-26" value={fy} onChange={(e) => setFy(e.target.value)}
        className="border border-paper-line rounded px-3 py-2 text-[13px]" />
      <input required type="date" value={reportingDate} onChange={(e) => setReportingDate(e.target.value)}
        className="border border-paper-line rounded px-3 py-2 text-[13px]" />
      <Button type="submit" variant="outline" disabled={busy}>+ New engagement</Button>
    </form>
  )
}
