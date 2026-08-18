import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useApp } from '../context/AppContext'
import { ErrorBanner } from '../components/ui'

export default function Login() {
  const { login } = useApp()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [mfaRequired, setMfaRequired] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const res = await login(email, password, totpCode)
      if (res.mfaRequired) {
        setMfaRequired(true)
      } else {
        navigate('/engagements')
      }
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-ink flex items-center justify-center">
      <div className="bg-card rounded-md w-[380px] p-8 border border-paper-line">
        <div className="font-mono text-[10px] tracking-[0.18em] text-gold mb-1">AUDIT OPERATING SYSTEM</div>
        <div className="font-serif text-[22px] text-ink mb-6">Sign in</div>
        <ErrorBanner message={error} />
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <input
            type="email" required placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)}
            className="border border-paper-line rounded px-3 py-2 text-[14px]"
          />
          <input
            type="password" required placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)}
            className="border border-paper-line rounded px-3 py-2 text-[14px]"
          />
          {mfaRequired && (
            <input
              type="text" required placeholder="6-digit authenticator code" value={totpCode}
              onChange={(e) => setTotpCode(e.target.value)}
              className="border border-gold rounded px-3 py-2 text-[14px]"
            />
          )}
          <button
            type="submit" disabled={busy}
            className="bg-ink text-white rounded px-3 py-2.5 text-[14px] font-medium mt-2 disabled:opacity-50"
          >
            {busy ? 'Signing in…' : mfaRequired ? 'Verify & sign in' : 'Sign in'}
          </button>
        </form>
        <div className="text-[13px] text-faint mt-4 text-center">
          No account? <Link to="/signup" className="text-gold">Create a firm</Link>
        </div>
      </div>
    </div>
  )
}
