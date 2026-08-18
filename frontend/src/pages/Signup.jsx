import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useApp } from '../context/AppContext'
import { ErrorBanner } from '../components/ui'

export default function Signup() {
  const { signup } = useApp()
  const navigate = useNavigate()
  const [form, setForm] = useState({ firm_name: '', admin_name: '', admin_email: '', admin_password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  function update(field) {
    return (e) => setForm((f) => ({ ...f, [field]: e.target.value }))
  }

  async function onSubmit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await signup(form)
      navigate('/engagements')
    } catch (err) {
      setError(err.message || 'Signup failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-ink flex items-center justify-center">
      <div className="bg-card rounded-md w-[400px] p-8 border border-paper-line">
        <div className="font-mono text-[10px] tracking-[0.18em] text-gold mb-1">AUDIT OPERATING SYSTEM</div>
        <div className="font-serif text-[22px] text-ink mb-6">Set up your firm</div>
        <ErrorBanner message={error} />
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <input required placeholder="Firm name" value={form.firm_name} onChange={update('firm_name')}
            className="border border-paper-line rounded px-3 py-2 text-[14px]" />
          <input required placeholder="Your name" value={form.admin_name} onChange={update('admin_name')}
            className="border border-paper-line rounded px-3 py-2 text-[14px]" />
          <input required type="email" placeholder="Email" value={form.admin_email} onChange={update('admin_email')}
            className="border border-paper-line rounded px-3 py-2 text-[14px]" />
          <input required type="password" placeholder="Password" value={form.admin_password} onChange={update('admin_password')}
            className="border border-paper-line rounded px-3 py-2 text-[14px]" />
          <button type="submit" disabled={busy}
            className="bg-ink text-white rounded px-3 py-2.5 text-[14px] font-medium mt-2 disabled:opacity-50">
            {busy ? 'Creating…' : 'Create firm'}
          </button>
        </form>
        <div className="text-[13px] text-faint mt-4 text-center">
          Already have an account? <Link to="/login" className="text-gold">Sign in</Link>
        </div>
      </div>
    </div>
  )
}
