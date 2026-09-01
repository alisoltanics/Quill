import React, { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'

interface Permission {
  id: number
  user_email: string
  role: 'owner' | 'editor' | 'viewer'
  granted_by: string
  created_at: string
}

interface ShareModalProps {
  docId: number
  docTitle: string
  onClose: () => void
}

const apiBase = () =>
  typeof window !== 'undefined'
    ? `${window.location.protocol}//${window.location.hostname}:8080/api`
    : 'http://localhost:8080/api'

export default function ShareModal({ docId, docTitle, onClose }: ShareModalProps) {
  const { accessToken, authFetch } = useAuth()
  const [permissions, setPermissions] = useState<Permission[]>([])
  const [loading, setLoading] = useState(true)
  const [userEmail, setUserEmail] = useState('')
  const [role, setRole] = useState<'editor' | 'viewer'>('viewer')
  const [error, setError] = useState<string | null>(null)
  const [sharing, setSharing] = useState(false)

  const hdrs = useCallback(() => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${accessToken}`,
  }), [accessToken])

  const fetchPermissions = useCallback(async () => {
    try {
      const resp = await authFetch(`${apiBase()}/documents/${docId}/permissions`, { headers: hdrs() })
      if (resp.ok) {
        const data = await resp.json()
        setPermissions(data.permissions ?? [])
      }
    } finally {
      setLoading(false)
    }
  }, [docId, hdrs, authFetch])

  useEffect(() => { fetchPermissions() }, [fetchPermissions])

  async function handleShare() {
    const email = userEmail.trim()
    if (!email || !email.includes('@')) {
      setError('Please enter a valid email')
      return
    }

    setError(null)
    setSharing(true)
    try {
      const resp = await authFetch(`${apiBase()}/documents/${docId}/share`, {
        method: 'POST',
        headers: hdrs(),
        body: JSON.stringify({ email, role }),
      })
      if (!resp.ok) {
        const data = await resp.json()
        setError(data.error || 'Failed to share')
        return
      }
      setUserEmail('')
      await fetchPermissions()
    } catch {
      setError('Network error')
    } finally {
      setSharing(false)
    }
  }

  async function handleUpdateRole(emailToUpdate: string, newRole: string) {
    const resp = await authFetch(`${apiBase()}/documents/${docId}/permissions/${encodeURIComponent(emailToUpdate)}`, {
      method: 'PATCH',
      headers: hdrs(),
      body: JSON.stringify({ role: newRole }),
    })
    if (resp.ok) {
      await fetchPermissions()
    }
  }

  async function handleRevoke(emailToRevoke: string) {
    const resp = await authFetch(`${apiBase()}/documents/${docId}/permissions/${encodeURIComponent(emailToRevoke)}`, {
      method: 'DELETE',
      headers: hdrs(),
    })
    if (resp.ok) {
      await fetchPermissions()
    }
  }

  return (
    <div className="share-overlay" onClick={onClose}>
      <div className="share-modal" onClick={e => e.stopPropagation()}>
        <div className="share-header">
          <div>
            <h3 className="share-title">Share &ldquo;{docTitle}&rdquo;</h3>
            <p className="share-subtitle">Invite collaborators by email</p>
          </div>
          <button className="share-close" onClick={onClose}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        {/* Share form */}
        <div className="share-form">
          <input
            className="share-input"
            type="email"
            placeholder="user@example.com"
            value={userEmail}
            onChange={e => { setUserEmail(e.target.value); setError(null) }}
            onKeyDown={e => { if (e.key === 'Enter') handleShare() }}
          />
          <select
            className="share-select"
            value={role}
            onChange={e => setRole(e.target.value as 'editor' | 'viewer')}
          >
            <option value="viewer">Viewer</option>
            <option value="editor">Editor</option>
          </select>
          <button
            className="btn btn--primary share-btn"
            onClick={handleShare}
            disabled={sharing || !userEmail}
          >
            {sharing ? 'Sharing…' : 'Share'}
          </button>
        </div>
        {error && <p className="share-error">{error}</p>}

        {/* Permissions list */}
        <div className="share-permissions">
          <h4 className="share-permissions-title">People with access</h4>
          {loading ? (
            <p className="share-empty">Loading…</p>
          ) : permissions.length === 0 ? (
            <p className="share-empty">No one else has access</p>
          ) : (
            <ul className="share-list">
              {permissions.map(perm => (
                <li key={perm.id} className="share-list-item">
                  <div className="share-list-user">
                    <div className="share-list-avatar">{perm.user_email[0]?.toUpperCase()}</div>
                    <span className="share-list-id">{perm.user_email}</span>
                    {perm.role === 'owner' && <span className="share-badge share-badge--owner">Owner</span>}
                  </div>
                  {perm.role !== 'owner' && (
                    <div className="share-list-actions">
                      <select
                        className="share-role-select"
                        value={perm.role}
                        onChange={e => handleUpdateRole(perm.user_email, e.target.value)}
                      >
                        <option value="viewer">Viewer</option>
                        <option value="editor">Editor</option>
                      </select>
                      <button
                        className="share-list-remove"
                        title="Remove access"
                        onClick={() => handleRevoke(perm.user_email)}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
