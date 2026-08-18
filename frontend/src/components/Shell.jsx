import { NavLink, useNavigate } from 'react-router-dom'
import { useApp } from '../context/AppContext'

const NAV = [
  { to: '/dashboard', label: 'Control Tower' },
  { to: '/data-centre', label: 'Data Centre' },
  { to: '/trial-balance', label: 'Trial Balance' },
  { to: '/gst', label: 'GST' },
  { to: '/tds', label: 'TDS' },
  { to: '/payroll', label: 'Payroll Statutory' },
  { to: '/bank', label: 'Bank' },
  { to: '/ap-ar', label: 'AP / AR' },
  { to: '/fixed-assets', label: 'Fixed Assets' },
  { to: '/inventory', label: 'Inventory' },
  { to: '/loans', label: 'Loans' },
  { to: '/investments', label: 'Investments' },
  { to: '/intercompany', label: 'Intercompany' },
  { to: '/risk', label: 'Risk Engine' },
  { to: '/exceptions', label: 'Exceptions' },
  { to: '/month-end-close', label: 'Month-End Close' },
  { to: '/working-papers', label: 'Working Papers' },
  { to: '/caro', label: 'CARO' },
  { to: '/ifc', label: 'IFC' },
  { to: '/ai-assistant', label: 'AI Assistant' },
]

export default function Shell({ children }) {
  const { user, logout, currentEngagementId } = useApp()
  const navigate = useNavigate()

  return (
    <div className="flex min-h-screen bg-paper">
      <div className="w-[230px] bg-ink text-white flex flex-col shrink-0">
        <div className="px-[18px] py-5 border-b border-ink-line">
          <div className="font-mono text-[10px] tracking-[0.18em] text-gold">AUDIT OPERATING SYSTEM</div>
          <div className="font-serif text-[19px] mt-1">Statutory Ledger</div>
        </div>
        <div className="px-2.5 py-2.5 flex-1 overflow-y-auto">
          {!currentEngagementId && (
            <div className="text-[11px] text-faint px-3 py-2 font-mono">Select an engagement to begin</div>
          )}
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `block px-3 py-2 mb-0.5 rounded text-[13px] border-l-2 ${
                  isActive ? 'bg-ink-2 text-white border-gold' : 'text-[#B7C1D6] border-transparent hover:bg-ink-2/60'
                } ${!currentEngagementId ? 'pointer-events-none opacity-40' : ''}`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </div>
        <div className="p-4 border-t border-ink-line">
          <button
            onClick={() => { logout(); navigate('/login') }}
            className="text-[12px] text-[#7C8AA6] hover:text-white"
          >
            Sign out
          </button>
        </div>
      </div>
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <div className="p-6 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  )
}

function TopBar() {
  const { currentEngagementId, setCurrentEngagementId, setCurrentClientId } = useApp()
  const navigate = useNavigate()
  return (
    <div className="px-7 py-4 border-b border-paper-line bg-card flex justify-between items-center">
      <div>
        <div className="font-mono text-[10.5px] tracking-[0.08em] text-faint uppercase">Engagement</div>
        <div className="font-serif text-[17px] text-ink">
          {currentEngagementId ? `#${currentEngagementId.slice(0, 8)}` : 'None selected'}
        </div>
      </div>
      <button
        onClick={() => {
          setCurrentEngagementId(null)
          setCurrentClientId(null)
          navigate('/engagements')
        }}
        className="text-[12px] font-mono text-gold border border-gold rounded px-3 py-1.5 hover:bg-gold-soft"
      >
        Switch Engagement
      </button>
    </div>
  )
}
