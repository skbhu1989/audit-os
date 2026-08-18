export function RiskBadge({ level }) {
  const map = {
    LOW: { c: 'text-green', bg: 'bg-green-soft', ring: 'ring-green/40' },
    MODERATE: { c: 'text-amber', bg: 'bg-amber-soft', ring: 'ring-amber/40' },
    MEDIUM: { c: 'text-amber', bg: 'bg-amber-soft', ring: 'ring-amber/40' },
    HIGH: { c: 'text-red', bg: 'bg-red-soft', ring: 'ring-red/40' },
    CRITICAL: { c: 'text-red', bg: 'bg-red-soft', ring: 'ring-red/60' },
    GREEN: { c: 'text-green', bg: 'bg-green-soft', ring: 'ring-green/40' },
    AMBER: { c: 'text-amber', bg: 'bg-amber-soft', ring: 'ring-amber/40' },
    RED: { c: 'text-red', bg: 'bg-red-soft', ring: 'ring-red/40' },
    NO_DATA: { c: 'text-faint', bg: 'bg-paper-line/40', ring: 'ring-faint/30' },
  }
  const s = map[level] || map.NO_DATA
  return (
    <span
      className={`inline-block font-mono text-[11px] tracking-wide font-bold px-2 py-0.5 rounded ring-1 ${s.c} ${s.bg} ${s.ring}`}
    >
      {level || 'N/A'}
    </span>
  )
}

export function StatusDot({ ok }) {
  if (ok === null || ok === undefined) return <span className="text-faint">—</span>
  return ok ? <span className="text-green font-bold">✓</span> : <span className="text-faint">·</span>
}

export function Card({ title, eyebrow, children, right }) {
  return (
    <div className="bg-card border border-paper-line rounded-md">
      {(title || eyebrow) && (
        <div className="flex items-baseline justify-between px-[18px] py-[14px] border-b border-paper-line">
          <div>
            {eyebrow && (
              <div className="font-mono text-[10.5px] tracking-[0.12em] text-gold uppercase mb-0.5">{eyebrow}</div>
            )}
            {title && <div className="font-serif text-[16px] text-ink">{title}</div>}
          </div>
          {right}
        </div>
      )}
      <div className="p-[18px]">{children}</div>
    </div>
  )
}

export function StatBlock({ label, value, sub, accent = 'gold' }) {
  const border = { gold: 'border-t-gold', red: 'border-t-red', green: 'border-t-green', amber: 'border-t-amber' }[accent]
  return (
    <div className={`p-4 bg-card border border-paper-line rounded-md border-t-[3px] ${border}`}>
      <div className="font-mono text-[10.5px] tracking-[0.08em] uppercase text-faint">{label}</div>
      <div className="font-serif text-[24px] text-ink mt-1">{value}</div>
      {sub && <div className="text-[12px] text-faint mt-0.5">{sub}</div>}
    </div>
  )
}

export function Table({ columns, rows, emptyText = 'No data yet.' }) {
  if (!rows || rows.length === 0) {
    return <div className="text-[13px] text-faint py-6 text-center">{emptyText}</div>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                className="text-left px-2.5 py-2 font-mono text-[10.5px] tracking-[0.08em] uppercase text-faint border-b-2 border-ink whitespace-nowrap"
                style={{ textAlign: c.align || 'left' }}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id || i} className={`border-b border-paper-line ${i % 2 ? 'bg-paper/60' : ''}`}>
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`px-2.5 py-2 whitespace-nowrap ${c.mono ? 'font-mono' : ''} ${c.muted ? 'text-faint' : ''}`}
                  style={{ textAlign: c.align || 'left' }}
                >
                  {c.render ? c.render(r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Button({ children, variant = 'primary', ...props }) {
  const styles = {
    primary: 'bg-ink text-white hover:bg-ink-2',
    outline: 'border border-gold text-gold bg-gold-soft hover:bg-gold/10',
    ghost: 'text-slate hover:bg-paper-line/50',
    danger: 'bg-red text-white hover:opacity-90',
  }
  return (
    <button
      {...props}
      className={`text-[13px] font-medium px-3.5 py-2 rounded disabled:opacity-40 disabled:cursor-not-allowed transition-colors ${styles[variant]} ${props.className || ''}`}
    >
      {children}
    </button>
  )
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-10 text-faint text-sm font-mono">
      Loading…
    </div>
  )
}

export function ErrorBanner({ message }) {
  if (!message) return null
  return (
    <div className="border border-red/40 bg-red-soft text-red text-[13px] px-3 py-2 rounded mb-3">
      {message}
    </div>
  )
}

export const inr = (n) => {
  if (n === null || n === undefined) return '—'
  return '₹' + Math.round(n).toLocaleString('en-IN')
}
