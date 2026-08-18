import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import { controlTower, preAudit } from '../api/client'
import { Card, StatBlock, RiskBadge, StatusDot, Spinner, ErrorBanner } from '../components/ui'

export default function Dashboard() {
  const { currentEngagementId } = useApp()
  const [tower, setTower] = useState(null)
  const [pre, setPre] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!currentEngagementId) return
    Promise.all([controlTower.get(currentEngagementId), preAudit.dashboard(currentEngagementId)])
      .then(([t, p]) => { setTower(t); setPre(p) })
      .catch((err) => setError(err.message))
  }, [currentEngagementId])

  if (!currentEngagementId) return <EmptyState />
  if (error) return <ErrorBanner message={error} />
  if (!tower || !pre) return <Spinner />

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-4 gap-3.5">
        <StatBlock label="Overall Status" value={pre.overall_status.replace('_', ' ')}
          accent={pre.overall_status === 'READY' ? 'green' : 'red'} />
        <StatBlock label="Data Coverage" value={`${pre.data_coverage_pct}%`}
          sub={`${pre.required_data_missing} required dataset(s) missing`} accent="gold" />
        <StatBlock label="Books Health" value={`${pre.books_health_score}/100`} accent={pre.books_health_score >= 70 ? 'green' : 'red'} />
        <StatBlock label="Critical Exceptions" value={pre.critical_exception_count} accent="red" />
      </div>

      {pre.blockers.length > 0 && (
        <Card title="Why am I not audit ready?" eyebrow="Blockers">
          <ul className="text-[13px] text-red flex flex-col gap-1">
            {pre.blockers.map((b, i) => <li key={i}>• {b}</li>)}
          </ul>
        </Card>
      )}

      <Card title="Universal Reconciliation Control Tower" eyebrow="Signature View — Books / Return / Payment / Document">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr>
                <th className="text-left px-2.5 py-2 font-mono text-[10.5px] tracking-[0.08em] uppercase text-faint border-b-2 border-ink">Area</th>
                <th className="px-2.5 py-2 font-mono text-[10.5px] tracking-[0.08em] uppercase text-faint border-b-2 border-ink">Books</th>
                <th className="px-2.5 py-2 font-mono text-[10.5px] tracking-[0.08em] uppercase text-faint border-b-2 border-ink">Return</th>
                <th className="px-2.5 py-2 font-mono text-[10.5px] tracking-[0.08em] uppercase text-faint border-b-2 border-ink">Payment</th>
                <th className="px-2.5 py-2 font-mono text-[10.5px] tracking-[0.08em] uppercase text-faint border-b-2 border-ink">Document</th>
                <th className="px-2.5 py-2 font-mono text-[10.5px] tracking-[0.08em] uppercase text-faint border-b-2 border-ink">Status</th>
                <th className="px-2.5 py-2 font-mono text-[10.5px] tracking-[0.08em] uppercase text-faint border-b-2 border-ink">Exceptions</th>
              </tr>
            </thead>
            <tbody>
              {tower.rows.map((r, i) => (
                <tr key={r.row} className={`border-b border-paper-line ${i % 2 ? 'bg-paper/60' : ''}`}>
                  <td className="px-2.5 py-2 font-medium">{r.row}</td>
                  <td className="px-2.5 py-2 text-center"><StatusDot ok={r.books} /></td>
                  <td className="px-2.5 py-2 text-center"><StatusDot ok={r.return_} /></td>
                  <td className="px-2.5 py-2 text-center"><StatusDot ok={r.payment} /></td>
                  <td className="px-2.5 py-2 text-center"><StatusDot ok={r.document} /></td>
                  <td className="px-2.5 py-2 text-center"><RiskBadge level={r.status} /></td>
                  <td className="px-2.5 py-2 font-mono text-faint">
                    {r.exception_count} {r.material_count > 0 && <span className="text-red">({r.material_count} material)</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Books Health Factors" eyebrow="Section 58">
        <ul className="text-[13px] text-slate flex flex-col gap-1">
          {pre.books_health_factors.map((f, i) => <li key={i}>• {f}</li>)}
        </ul>
      </Card>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="text-center py-20 text-faint">
      <div className="font-serif text-[18px] mb-2">No engagement selected</div>
      <div className="text-[13px]">Choose a client and engagement to see the Control Tower.</div>
    </div>
  )
}
