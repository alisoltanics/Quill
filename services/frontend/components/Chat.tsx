import React, { useEffect, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import Editor, { EditorHandle } from './Editor'
import { useAuth } from '../context/AuthContext'
import * as Y from 'yjs'
import { base64ToBytes, bytesToBase64, createYjsGatewayConnection } from '../lib/yjsGateway'

const DiagramEditor = dynamic(() => import('./DiagramEditor'), { ssr: false })

type Mode = 'write' | 'diagram'
type ExportFormat = 'txt' | 'markdown' | 'html'

interface ChatProps {
  docId: number
  docTitle: string
}

export default function Chat({ docId, docTitle }: ChatProps) {
  const { accessToken, authFetch } = useAuth()
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
  const clientIdRef = useRef<string>(Math.random().toString(36).slice(2))
  const saveTimerRef = useRef<number | null>(null)

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
    })

    return () => {
      connection.close()
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
    }
  }, [])

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
        </div>

        <div className="export-group">
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
            />
          )}

          <div className="actions">
            <div className="status">{statusMsg}</div>
            <div style={{ flex: 1 }} />
            <button className="btn btn--primary" onClick={save} disabled={saving || !hydrated}>
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </>
      ) : (
        <DiagramEditor docId={docId} />
      )}
    </div>
  )
}
