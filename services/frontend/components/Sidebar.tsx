import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import ShareModal from './ShareModal'

export interface DocMeta {
  id: number
  folder_id: number | null
  title: string
  updated_at: string
  role?: string
  granted_by?: string
}

export interface FolderMeta {
  id: number
  name: string
  documents: DocMeta[]
}

interface SidebarProps {
  activeDocId: number | null
  onSelect: (doc: DocMeta) => void
  onDocsLoaded?: (docs: DocMeta[]) => void
}

const apiBase = () =>
  typeof window !== 'undefined'
    ? `${window.location.protocol}//${window.location.hostname}:8080/api`
    : 'http://localhost:8080/api'

// Unique id per logical create attempt. Sent as an Idempotency-Key header so
// the document service can de-duplicate retried folder creation.
function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `f-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

// ─── Inline rename input ────────────────────────────────────────────────────

function RenameInput({ value, onCommit }: { value: string; onCommit: (v: string) => void }) {
  const [val, setVal] = useState(value)
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => { ref.current?.focus(); ref.current?.select() }, [])
  return (
    <input
      ref={ref}
      className="sidebar-rename"
      value={val}
      onChange={e => setVal(e.target.value)}
      onBlur={() => onCommit(val.trim() || value)}
      onKeyDown={e => {
        if (e.key === 'Enter') onCommit(val.trim() || value)
        if (e.key === 'Escape') onCommit(value)
      }}
      onClick={e => e.stopPropagation()}
    />
  )
}

// ─── SVG icons ─────────────────────────────────────────────────────────────

const IconEdit = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
  </svg>
)

const IconTrash = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
    <path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
  </svg>
)

const IconDocAdd = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
    <line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/>
  </svg>
)

const IconChevron = ({ open }: { open: boolean }) => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
    style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.15s' }}>
    <polyline points="9 18 15 12 9 6"/>
  </svg>
)

const IconFolder = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
  </svg>
)

const IconDoc = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
  </svg>
)

const IconShare = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
  </svg>
)

const IconLink = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
  </svg>
)

// ─── Doc row ────────────────────────────────────────────────────────────────

function DocRow({ doc, active, onSelect, onRename, onDelete, onShare, indented }: {
  doc: DocMeta
  active: boolean
  onSelect: () => void
  onRename: (v: string) => void
  onDelete: () => void
  onShare?: () => void
  indented?: boolean
}) {
  const [renaming, setRenaming] = useState(false)

  return (
    <li
      className={`sidebar-item sidebar-item--doc${active ? ' sidebar-item--active' : ''}${indented ? ' sidebar-item--indented' : ''}`}
      onClick={onSelect}
    >
      <span className="sidebar-item-icon">
        {doc.role ? <IconLink /> : <IconDoc />}
      </span>
      {renaming ? (
        <RenameInput value={doc.title} onCommit={v => { setRenaming(false); onRename(v) }} />
      ) : (
        <>
          <div className="sidebar-item-body">
            <span className="sidebar-item-title">{doc.title}</span>
            {doc.role && <span className="sidebar-item-role">Shared as {doc.role} by {doc.granted_by}</span>}
          </div>
          <div className="sidebar-item-actions">
            {onShare && !doc.role && (
              <button className="sidebar-action-btn" title="Share" onClick={e => { e.stopPropagation(); onShare() }}>
                <IconShare />
              </button>
            )}
            {!doc.role && (
              <>
                <button className="sidebar-action-btn" title="Rename" onClick={e => { e.stopPropagation(); setRenaming(true) }}>
                  <IconEdit />
                </button>
                <button className="sidebar-action-btn sidebar-action-btn--danger" title="Delete" onClick={e => { e.stopPropagation(); onDelete() }}>
                  <IconTrash />
                </button>
              </>
            )}
          </div>
        </>
      )}
    </li>
  )
}

// ─── Folder row ─────────────────────────────────────────────────────────────

function FolderRow({ folder, activeDocId, onSelectDoc, onRenameFolder, onDeleteFolder, onAddDoc, onRenameDoc, onDeleteDoc, onShareDoc }: {
  folder: FolderMeta
  activeDocId: number | null
  onSelectDoc: (doc: DocMeta) => void
  onRenameFolder: (name: string) => void
  onDeleteFolder: () => void
  onAddDoc: () => void
  onRenameDoc: (id: number, title: string) => void
  onDeleteDoc: (id: number) => void
  onShareDoc?: (doc: DocMeta) => void
}) {
  const [open, setOpen] = useState(true)
  const [renaming, setRenaming] = useState(false)

  return (
    <li className="sidebar-folder">
      {/* Folder header */}
      <div className="sidebar-item sidebar-item--folder" onClick={() => setOpen(o => !o)}>
        <span className="sidebar-item-chevron"><IconChevron open={open} /></span>
        <span className="sidebar-item-icon folder-icon"><IconFolder /></span>
        {renaming ? (
          <RenameInput value={folder.name} onCommit={v => { setRenaming(false); onRenameFolder(v) }} />
        ) : (
          <>
            <div className="sidebar-item-body">
              <span className="sidebar-item-title">{folder.name}</span>
              <span className="sidebar-item-date">{folder.documents.length} doc{folder.documents.length !== 1 ? 's' : ''}</span>
            </div>
            <div className="sidebar-item-actions">
              <button className="sidebar-action-btn" title="New document in folder" onClick={e => { e.stopPropagation(); onAddDoc() }}>
                <IconDocAdd />
              </button>
              <button className="sidebar-action-btn" title="Rename folder" onClick={e => { e.stopPropagation(); setRenaming(true) }}>
                <IconEdit />
              </button>
              <button className="sidebar-action-btn sidebar-action-btn--danger" title="Delete folder" onClick={e => { e.stopPropagation(); onDeleteFolder() }}>
                <IconTrash />
              </button>
            </div>
          </>
        )}
      </div>

      {/* Folder documents */}
      {open && folder.documents.length > 0 && (
        <ul className="sidebar-folder-docs">
          {folder.documents.map(doc => (
            <DocRow
              key={doc.id}
              doc={doc}
              active={doc.id === activeDocId}
              onSelect={() => onSelectDoc(doc)}
              onRename={title => onRenameDoc(doc.id, title)}
              onDelete={() => onDeleteDoc(doc.id)}
              onShare={onShareDoc ? () => onShareDoc(doc) : undefined}
              indented
            />
          ))}
        </ul>
      )}
      {open && folder.documents.length === 0 && (
        <p className="sidebar-folder-empty">Empty folder</p>
      )}
    </li>
  )
}

// ─── Sidebar ────────────────────────────────────────────────────────────────

export default function Sidebar({ activeDocId, onSelect, onDocsLoaded }: SidebarProps) {
  const { accessToken, authFetch } = useAuth()
  const [folders, setFolders] = useState<FolderMeta[]>([])
  const [rootDocs, setRootDocs] = useState<DocMeta[]>([])
  const [sharedDocs, setSharedDocs] = useState<DocMeta[]>([])
  const [loading, setLoading] = useState(true)
  const [shareDoc, setShareDoc] = useState<DocMeta | null>(null)
  // Reused while a folder-create request is unresolved so a double-click or
  // network retry cannot create duplicate folders server-side.
  const folderCreateKeyRef = useRef<string | null>(null)

  const hdrs = useCallback(() => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${accessToken}`,
  }), [accessToken])

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const [docsResp, sharedResp] = await Promise.all([
        authFetch(`${apiBase()}/documents`, { headers: hdrs() }),
        authFetch(`${apiBase()}/shared-with-me`, { headers: hdrs() }),
      ])
      let nextFolders: FolderMeta[] = []
      let nextRootDocs: DocMeta[] = []
      if (docsResp.ok) {
        const data = await docsResp.json()
        nextFolders = data.folders ?? []
        nextRootDocs = data.documents ?? []
        setFolders(nextFolders)
        setRootDocs(nextRootDocs)
      }
      let nextSharedDocs: DocMeta[] = []
      if (sharedResp.ok) {
        const data = await sharedResp.json()
        nextSharedDocs = data.documents ?? []
        setSharedDocs(nextSharedDocs)
      }
      onDocsLoaded?.([
        ...nextRootDocs,
        ...nextFolders.flatMap((folder: FolderMeta) => folder.documents ?? []),
        ...nextSharedDocs,
      ])
    } finally {
      setLoading(false)
    }
  }, [hdrs, onDocsLoaded, authFetch])

  useEffect(() => { fetchAll() }, [fetchAll])

  // ── Folder actions ──────────────────────────────────────────────────────

  async function createFolder() {
    if (!folderCreateKeyRef.current) {
      folderCreateKeyRef.current = newIdempotencyKey()
    }
    const key = folderCreateKeyRef.current
    try {
      const resp = await authFetch(`${apiBase()}/folders`, {
        method: 'POST',
        headers: { ...hdrs(), 'Idempotency-Key': key },
        body: JSON.stringify({ name: 'New Folder' }),
      })
      if (!resp.ok) return
      const folder = await resp.json()
      // Guard against an idempotent replay response re-adding a folder we
      // already hold locally.
      setFolders(prev =>
        prev.some(f => f.id === folder.id)
          ? prev
          : [...prev, { ...folder, documents: [] }],
      )
    } finally {
      folderCreateKeyRef.current = null
    }
  }

  async function renameFolder(id: number, name: string) {
    await authFetch(`${apiBase()}/folders/${id}`, {
      method: 'PATCH', headers: hdrs(), body: JSON.stringify({ name }),
    })
    setFolders(prev => prev.map(f => f.id === id ? { ...f, name } : f))
  }

  async function deleteFolder(id: number) {
    await authFetch(`${apiBase()}/folders/${id}`, { method: 'DELETE', headers: hdrs() })
    // Docs become root-level (SET_NULL) — refetch to get updated list
    await fetchAll()
    if (folders.find(f => f.id === id)?.documents.some(d => d.id === activeDocId)) {
      onSelect({ id: -1, folder_id: null, title: '', updated_at: '' })
    }
  }

  // ── Document actions ────────────────────────────────────────────────────

  async function createDoc(folderId?: number) {
    const resp = await authFetch(`${apiBase()}/documents`, {
      method: 'POST',
      headers: hdrs(),
      body: JSON.stringify({ title: 'Untitled', folder_id: folderId ?? null }),
    })
    if (!resp.ok) return
    const doc: DocMeta = await resp.json()
    if (folderId) {
      setFolders(prev => prev.map(f =>
        f.id === folderId ? { ...f, documents: [doc, ...f.documents] } : f
      ))
    } else {
      setRootDocs(prev => [doc, ...prev])
    }
    onSelect(doc)
  }

  async function renameDoc(id: number, title: string, inFolderId?: number) {
    await authFetch(`${apiBase()}/documents/${id}`, {
      method: 'PATCH', headers: hdrs(), body: JSON.stringify({ title }),
    })
    if (inFolderId) {
      setFolders(prev => prev.map(f =>
        f.id === inFolderId
          ? { ...f, documents: f.documents.map(d => d.id === id ? { ...d, title } : d) }
          : f
      ))
    } else {
      setRootDocs(prev => prev.map(d => d.id === id ? { ...d, title } : d))
    }
  }

  async function deleteDoc(id: number, inFolderId?: number) {
    await authFetch(`${apiBase()}/documents/${id}`, { method: 'DELETE', headers: hdrs() })
    if (inFolderId) {
      setFolders(prev => prev.map(f =>
        f.id === inFolderId ? { ...f, documents: f.documents.filter(d => d.id !== id) } : f
      ))
    } else {
      setRootDocs(prev => prev.filter(d => d.id !== id))
    }
    if (id === activeDocId) onSelect({ id: -1, folder_id: null, title: '', updated_at: '' })
  }

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-title">Documents</span>
        <div className="sidebar-header-actions">
          <button className="sidebar-new" title="New folder" onClick={createFolder}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              <line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/>
            </svg>
          </button>
          <button className="sidebar-new" title="New document" onClick={() => createDoc()}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/>
            </svg>
          </button>
        </div>
      </div>

      {loading ? (
        <p className="sidebar-empty">Loading…</p>
      ) : (
        <ul className="sidebar-list">
          {/* Folders */}
          {folders.map(folder => (
            <FolderRow
              key={folder.id}
              folder={folder}
              activeDocId={activeDocId}
              onSelectDoc={onSelect}
              onRenameFolder={name => renameFolder(folder.id, name)}
              onDeleteFolder={() => deleteFolder(folder.id)}
              onAddDoc={() => createDoc(folder.id)}
              onRenameDoc={(id, title) => renameDoc(id, title, folder.id)}
              onDeleteDoc={id => deleteDoc(id, folder.id)}
              onShareDoc={doc => setShareDoc(doc)}
            />
          ))}

          {/* Root-level docs */}
          {rootDocs.map(doc => (
            <DocRow
              key={doc.id}
              doc={doc}
              active={doc.id === activeDocId}
              onSelect={() => onSelect(doc)}
              onRename={title => renameDoc(doc.id, title)}
              onDelete={() => deleteDoc(doc.id)}
              onShare={() => setShareDoc(doc)}
            />
          ))}

          {folders.length === 0 && rootDocs.length === 0 && (
            <p className="sidebar-empty">No documents yet</p>
          )}
        </ul>
      )}

      {/* Shared with me */}
      {!loading && sharedDocs.length > 0 && (
        <div className="sidebar-shared">
          <div className="sidebar-shared-header">
            <IconLink />
            <span className="sidebar-shared-title">Shared with me</span>
          </div>
          <ul className="sidebar-list sidebar-list--shared">
            {sharedDocs.map(doc => (
              <DocRow
                key={doc.id}
                doc={doc}
                active={doc.id === activeDocId}
                onSelect={() => onSelect(doc)}
                onRename={() => {}}
                onDelete={() => {}}
              />
            ))}
          </ul>
        </div>
      )}

      {/* Share modal */}
      {shareDoc && (
        <ShareModal
          docId={shareDoc.id}
          docTitle={shareDoc.title}
          onClose={() => { setShareDoc(null); fetchAll() }}
        />
      )}
    </aside>
  )
}
