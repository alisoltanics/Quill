import React, { useEffect, useRef, useState } from 'react'

// Realtime document editor: contenteditable editor with WebSocket sync

export default function Chat() {
  const wsRef = useRef<WebSocket | null>(null)
  const editorRef = useRef<HTMLDivElement | null>(null)
  const [connected, setConnected] = useState(false)
  const [saving, setSaving] = useState(false)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const clientIdRef = useRef<string>(Math.random().toString(36).slice(2))
  const reconnectRef = useRef<number>(0)

  const WS_URL = (() => {
    if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL
    if (typeof window !== 'undefined') {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      return `${proto}//${window.location.hostname}:8080/ws`
    }
    return 'ws://localhost:8080/ws'
  })()

  useEffect(() => {
    let mounted = true

    async function fetchInitial() {
      try {
        if (typeof window === 'undefined') return
        const host = window.location.hostname
        const resp = await fetch(`${window.location.protocol}//${host}:8080/document`)
        if (!resp.ok) return
        const data = await resp.json()
        if (mounted && data && data.content && editorRef.current) {
          editorRef.current.innerHTML = String(data.content)
        }
      } catch (e) {
        // ignore
      }
    }
    fetchInitial()

    function connect() {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        if (!mounted) return
        setConnected(true)
        reconnectRef.current = 0
      }

      ws.onmessage = (ev) => {
        try {
          const payload = typeof ev.data === 'string' ? JSON.parse(ev.data) : {}
          if (mounted && payload && payload.content && editorRef.current) {
            editorRef.current.innerHTML = String(payload.content)
            setStatusMsg('Saved by server')
            setTimeout(() => setStatusMsg(null), 1500)
          }
        } catch (e) {
          // ignore
        }
      }

      ws.onclose = () => {
        if (!mounted) return
        setConnected(false)
        reconnectRef.current = Math.min(10, reconnectRef.current + 1)
        const delay = Math.min(30000, 500 * 2 ** reconnectRef.current)
        setTimeout(() => connect(), delay)
      }

      ws.onerror = (e) => {
        console.error('ws error', e)
        ws.close()
      }
    }

    connect()

    return () => {
      mounted = false
      if (wsRef.current) wsRef.current.close()
    }
  }, [WS_URL])

  function exec(cmd: string) {
    document.execCommand(cmd)
    if (editorRef.current) editorRef.current.focus()
  }

  function save() {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setStatusMsg('Disconnected — cannot save')
      return
    }
    if (!editorRef.current) return
    const html = editorRef.current.innerHTML
    const payload = { clientId: clientIdRef.current, text: html, full: true }
    try {
      setSaving(true)
      wsRef.current.send(JSON.stringify(payload))
      setStatusMsg('Saving...')
    } catch (e) {
      setStatusMsg('Save failed')
    } finally {
      setSaving(false)
      setTimeout(() => setStatusMsg(null), 2000)
    }
  }

  return (
    <div className="app-shell">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Realtime Collaborative Document</h2>
        <div style={{ textAlign: 'right' }}>
          <div className="status">Status: {connected ? 'connected' : 'disconnected'}</div>
        </div>
      </div>

      <div className="card">
        <div className="editor-toolbar">
          <button onClick={() => exec('bold')} title="Bold"><strong>B</strong></button>
          <button onClick={() => exec('italic')} title="Italic"><em>I</em></button>
          <button onClick={() => exec('insertUnorderedList')} title="Bulleted list">• List</button>
          <button onClick={() => exec('formatBlock', 'pre' as any)} title="Code">Code</button>
          <div style={{ flex: 1 }} />
          <div className="status">{statusMsg}</div>
        </div>

        <div
          className="editor"
          ref={editorRef}
          contentEditable
          suppressContentEditableWarning
          aria-label="Document editor"
        />

        <div className="actions">
          <div style={{ flex: 1 }} />
          <button className="save-btn" onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
        </div>
      </div>
    </div>
  )
}
