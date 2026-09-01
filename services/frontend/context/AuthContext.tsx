import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

interface AuthState {
  accessToken: string | null
  email: string | null
}

interface AuthContextValue extends AuthState {
  ready: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
  authFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const AUTH_URL =
  typeof window !== 'undefined'
    ? `${window.location.protocol}//${window.location.hostname}:8002`
    : 'http://localhost:8002'

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ accessToken: null, email: null })
  const [ready, setReady] = useState(false)
  const refreshInFlightRef = useRef<Promise<string | null> | null>(null)

  // Restore from localStorage on mount (best-effort)
  useEffect(() => {
    const token = localStorage.getItem('access_token')
    const email = localStorage.getItem('user_email')
    if (token && email) setState({ accessToken: token, email })
    setReady(true)
  }, [])

  const _storeTokens = (access: string, refresh: string, email: string) => {
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
    localStorage.setItem('user_email', email)
    setState({ accessToken: access, email })
  }

  const login = useCallback(async (email: string, password: string) => {
    const resp = await fetch(`${AUTH_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail ?? 'Login failed')
    }
    const data = await resp.json()
    _storeTokens(data.access_token, data.refresh_token, email)
  }, [])

  const register = useCallback(async (email: string, password: string) => {
    const resp = await fetch(`${AUTH_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail ?? 'Registration failed')
    }
    const data = await resp.json()
    _storeTokens(data.access_token, data.refresh_token, email)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user_email')
    setState({ accessToken: null, email: null })
  }, [])

  const refreshAccessToken = useCallback(async () => {
    if (refreshInFlightRef.current) return refreshInFlightRef.current

    const refreshToken = localStorage.getItem('refresh_token')
    const email = localStorage.getItem('user_email')
    if (!refreshToken || !email) {
      return null
    }

    const refreshPromise = (async () => {
      try {
        const resp = await fetch(`${AUTH_URL}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        })
        if (!resp.ok) return null

        const data = await resp.json()
        if (!data?.access_token || !data?.refresh_token) return null
        _storeTokens(data.access_token, data.refresh_token, email)
        return String(data.access_token)
      } catch {
        return null
      } finally {
        refreshInFlightRef.current = null
      }
    })()

    refreshInFlightRef.current = refreshPromise
    return refreshPromise
  }, [])

  const authFetch = useCallback(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const resp = await fetch(input, init)
    if (resp.status !== 401) {
      return resp
    }

    const newAccessToken = await refreshAccessToken()
    if (newAccessToken) {
      window.location.reload()
      return resp
    }

    logout()
    window.location.href = '/login'
    return resp
  }, [logout, refreshAccessToken])

  return (
    <AuthContext.Provider value={{ ...state, ready, login, register, logout, authFetch }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
