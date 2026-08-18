import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { setToken, auth as authApi } from '../api/client'

const AppContext = createContext(null)

export function AppProvider({ children }) {
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem('current_user')
    return raw ? JSON.parse(raw) : null
  })
  const [currentClientId, setCurrentClientId] = useState(() => localStorage.getItem('current_client_id') || null)
  const [currentEngagementId, setCurrentEngagementId] = useState(() => localStorage.getItem('current_engagement_id') || null)

  useEffect(() => {
    if (currentClientId) localStorage.setItem('current_client_id', currentClientId)
    else localStorage.removeItem('current_client_id')
  }, [currentClientId])

  useEffect(() => {
    if (currentEngagementId) localStorage.setItem('current_engagement_id', currentEngagementId)
    else localStorage.removeItem('current_engagement_id')
  }, [currentEngagementId])

  const login = useCallback(async (email, password, totpCode) => {
    const res = await authApi.login({ email, password, totp_code: totpCode || undefined })
    if (res.mfa_required) return { mfaRequired: true }
    setToken(res.access_token)
    const u = { role: res.role }
    setUser(u)
    localStorage.setItem('current_user', JSON.stringify(u))
    return { mfaRequired: false }
  }, [])

  const signup = useCallback(async (data) => {
    const res = await authApi.signup(data)
    setToken(res.access_token)
    const u = { role: 'FIRM_ADMIN' }
    setUser(u)
    localStorage.setItem('current_user', JSON.stringify(u))
    return res
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    setCurrentClientId(null)
    setCurrentEngagementId(null)
    localStorage.removeItem('current_user')
  }, [])

  return (
    <AppContext.Provider
      value={{
        user, login, signup, logout,
        currentClientId, setCurrentClientId,
        currentEngagementId, setCurrentEngagementId,
      }}
    >
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
