import React, { useCallback, useEffect, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import Editor, { EditorHandle } from './Editor'
import { useAuth } from '../context/AuthContext'
import * as Y from 'yjs'
import { base64ToBytes, bytesToBase64, createYjsGatewayConnection, CursorData } from '../lib/yjsGateway'

const DiagramEditor = dynamic(() => import('./DiagramEditor'), { ssr: false })

type Mode = 'write' | 'diagram'
type ExportFormat = 'txt' | 'markdown' | 'html'

interface ChatProps {
  docId: number
  docTitle: string
  role?: string
}

export default function Chat({ docId, docTitle, role }: ChatProps) {
  const isViewer = role === 'viewer'
  const { accessToken, authFetch, email } = useAuth()
  const editorRef = useRef<EditorHandle | null>(null)
  const ydocRef = useRef(new Y.Doc())
  const [connected, setConnected] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [exportFormat, setExportFormat] = useState<ExportFormat>('txt')
  const [mode, setMode] = useState<Mode>('write')
  const [hydrated, setHydrated] = useState(false)
  const [serverContent, setServerContent] = useState('')
  const [onlineUsers, setOnlineUsers] = useState<string[]>([])
  const [remoteCursors, setRemoteCursors] = useState<CursorData[]>([])
  const [showOnlineDropdown, setShowOnlineDropdown] = useState(false)
  const onlineDropdownRef = useRef<HTMLDivElement>(null)
  const clientIdRef = useRef<string>(Math.random().toString(36).slice(2))
  const saveTimerRef = useRef<number | null>(null)
  const sendCursorUpdateRef = useRef<((cursor: CursorData) => void) | null>(null)
  const cursorTimerRef = useRef<number | null>(null)

  const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost'
  const apiBase = typeof window !== 'undefined'
    ? `${window.location.protocol}//${host}:8080/api`
    : 'http://localhost:8080/api'
  const WS_URL = (() => {
    if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL
    const proto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${host}:8080/ws`
  })()

  useEffect(() => {
    if (!hydrated) return
    const connection = createYjsGatewayConnection({
      doc: ydocRef.current,
      docId,
      clientId: clientIdRef.current,
      wsUrl: WS_URL,
      token: accessToken ?? undefined,
      onStatus: setConnected,
      onLocalDocumentUpdate: scheduleSave,
      onPresenceUpdate: setOnlineUsers,
      onCursorUpdate: (cursor) => {
        setRemoteCursors(prev => {
          const filtered = prev.filter(c => c.email !== cursor.email)
          return [...filtered, cursor]
        })
      },
    })

    sendCursorUpdateRef.current = connection.sendCursorUpdate

    return () => {
      connection.close()
      sendCursorUpdateRef.current = null
    }
  }, [hydrated, docId, WS_URL, accessToken])

  useEffect(() => {
    async function fetchInitial() {
      try {
        const resp = await authFetch(`${apiBase}/documents/${docId}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        })
        if (!resp.ok) return
        const data = await resp.json()
        setServerContent(typeof data?.content === 'string' ? data.content : '')
        if (data?.yjs_state) {
          try {
            Y.applyUpdate(ydocRef.current, base64ToBytes(String(data.yjs_state)))
          } catch {
            // Fallback to serverContent rendering when stored yjs_state is malformed.
          }
        }
      } catch { /* ignore */ }
      finally {
        setHydrated(true)
      }
    }

    fetchInitial()
  }, [docId, accessToken, apiBase])

  useEffect(() => {
    return () => {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current)
      }
      if (cursorTimerRef.current !== null) {
        window.clearTimeout(cursorTimerRef.current)
      }
    }
  }, [])

  const handleCursorChange = useCallback((position: number) => {
    if (cursorTimerRef.current !== null) return
    cursorTimerRef.current = window.setTimeout(() => {
      cursorTimerRef.current = null
      sendCursorUpdateRef.current?.({
        email: email ?? '',
        position,
      })
    }, 30)
  }, [email])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (onlineDropdownRef.current && !onlineDropdownRef.current.contains(e.target as Node)) {
        setShowOnlineDropdown(false)
      }
    }
    if (showOnlineDropdown) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showOnlineDropdown])

  function scheduleSave() {
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current)
    }
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null
      void save()
    }, 250)
  }

  async function save() {
    const html = editorRef.current?.getHTML() ?? ''
    const yjsState = bytesToBase64(Y.encodeStateAsUpdate(ydocRef.current))
    setSaving(true)
    try {
      const resp = await authFetch(`${apiBase}/documents/${docId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ content: html, yjs_state: yjsState, full: true, clientId: clientIdRef.current }),
      })
      setStatusMsg(resp.ok ? 'Saved' : 'Save failed')
    } catch {
      setStatusMsg('Save failed')
    } finally {
      setSaving(false)
      setTimeout(() => setStatusMsg(null), 2000)
    }
  }

  async function exportDocument() {
    const html = editorRef.current?.getHTML() ?? serverContent ?? ''
    if (!html.trim()) {
      setStatusMsg('Nothing to export')
      setTimeout(() => setStatusMsg(null), 2000)
      return
    }

    setExporting(true)
    try {
      const resp = await authFetch(`${apiBase}/export?format=${encodeURIComponent(exportFormat)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ content: html }),
      })

      if (!resp.ok) {
        setStatusMsg('Export failed')
        return
      }

      const blob = await resp.blob()
      const ext = exportFormat === 'markdown' ? 'md' : exportFormat
      const safeTitle = (docTitle || `document-${docId}`).trim().replace(/[^a-zA-Z0-9-_]+/g, '_')
      const fileName = `${safeTitle}.${ext}`

      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)

      setStatusMsg(`Exported as ${ext}`)
    } catch {
      setStatusMsg('Export failed')
    } finally {
      setExporting(false)
      setTimeout(() => setStatusMsg(null), 2000)
    }
  }

  return (
    <div className="card editor-card">
      <div className="editor-toolbar" style={{ justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
          <strong style={{ fontSize: 14, color: '#111827', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{docTitle}</strong>
          <span className="status">{connected ? 'Connected' : 'Reconnecting...'}</span>
          {isViewer && <span style={{ fontSize: 11, color: '#6b7280', background: '#f3f4f6', padding: '2px 8px', borderRadius: 4 }}>Viewer</span>}
          {onlineUsers.length > 0 && (
            <div ref={onlineDropdownRef} style={{ position: 'relative' }}>
              <button
                type="button"
                onClick={() => setShowOnlineDropdown(v => !v)}
                style={{
                  fontSize: 11, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 4,
                  background: 'none', border: 'none', cursor: 'pointer', padding: '2px 6px', borderRadius: 4,
                }}
              >
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#22c55e', display: 'inline-block' }} />
                {onlineUsers.length} online
              </button>
              {showOnlineDropdown && (
                <div style={{
                  position: 'absolute', top: '100%', left: 0, marginTop: 4,
                  background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
                  boxShadow: '0 4px 12px rgba(0,0,0,0.1)', minWidth: 200, zIndex: 50,
                  padding: 4,
                }}>
                  {onlineUsers.map(email => (
                    <div key={email} style={{
                      fontSize: 12, color: '#374151', padding: '6px 10px', borderRadius: 4,
                      display: 'flex', alignItems: 'center', gap: 8,
                    }}>
                      <span style={{
                        width: 24, height: 24, borderRadius: '50%', background: '#e0e7ff',
                        color: '#4f46e5', display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 11, fontWeight: 600, flexShrink: 0,
                      }}>
                        {email[0]?.toUpperCase()}
                      </span>
                      {email}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="export-group">
          {!isViewer && (
            <>
              <span className="export-label">Mode</span>
              <button
                type="button"
                className={`btn${mode === 'write' ? ' btn--primary' : ''}`}
                onClick={() => setMode('write')}
              >
                Write
              </button>
              <button
                type="button"
                className={`btn${mode === 'diagram' ? ' btn--primary' : ''}`}
                onClick={() => setMode('diagram')}
              >
                Diagram
              </button>
            </>
          )}

          <span className="export-label" style={{ marginLeft: 8 }}>Export</span>
          <select
            className="input"
            value={exportFormat}
            onChange={e => setExportFormat(e.target.value as ExportFormat)}
            style={{ width: 110, height: 32 }}
            disabled={exporting || !hydrated || mode !== 'write'}
          >
            <option value="txt">Text (.txt)</option>
            <option value="markdown">Markdown (.md)</option>
            <option value="html">HTML (.html)</option>
          </select>
          <button
            type="button"
            className="btn"
            onClick={exportDocument}
            disabled={exporting || !hydrated || mode !== 'write'}
          >
            {exporting ? 'Exporting...' : 'Export'}
          </button>
        </div>
      </div>

      {mode === 'write' ? (
        <>
          {!hydrated ? (
            <div className="tiptap-wrapper" style={{ minHeight: 240, display: 'grid', placeItems: 'center' }}>
              <span className="status">Loading document...</span>
            </div>
          ) : (
            <Editor
              key={docId}
              ref={editorRef}
              ydoc={ydocRef.current}
              initialContent={serverContent}
              editable={!isViewer}
              remoteCursors={remoteCursors}
              onCursorChange={isViewer ? undefined : handleCursorChange}
            />
          )}

          {!isViewer && (
            <div className="actions">
              <div className="status">{statusMsg}</div>
              <div style={{ flex: 1 }} />
              <button className="btn btn--primary" onClick={save} disabled={saving || !hydrated}>
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          )}
        </>
      ) : (
        <DiagramEditor docId={docId} />
      )}
    </div>
  )
}
