import Head from 'next/head'
import { useRouter } from 'next/router'
import { useEffect, useState } from 'react'
import dynamic from 'next/dynamic'
import { useAuth } from '../context/AuthContext'
import Sidebar, { DocMeta } from '../components/Sidebar'

const Chat = dynamic(() => import('../components/Chat'), { ssr: false })

const APP_NAME = 'Quill'
const APP_TAGLINE = 'Collaborative Writing'

export default function Home() {
  const { accessToken, email, logout, ready } = useAuth()
  const router = useRouter()
  const [activeDoc, setActiveDoc] = useState<DocMeta | null>(null)
  const [availableDocs, setAvailableDocs] = useState<DocMeta[]>([])

  const requestedDocId = (() => {
    const raw = router.query.doc
    const value = Array.isArray(raw) ? raw[0] : raw
    if (!value) return null
    const parsed = Number(value)
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null
  })()

  useEffect(() => {
    if (ready && !accessToken) router.replace('/login')
  }, [ready, accessToken, router])

  useEffect(() => {
    if (!router.isReady) return
    if (requestedDocId === null) {
      setActiveDoc(null)
      return
    }

    const matchedDoc = availableDocs.find(doc => doc.id === requestedDocId) ?? null
    setActiveDoc(matchedDoc)
  }, [router.isReady, requestedDocId, availableDocs])

  function handleSelect(doc: DocMeta | null) {
    setActiveDoc(doc)
    void router.replace(
      doc
        ? { pathname: '/', query: { doc: doc.id } }
        : { pathname: '/' },
      undefined,
      { shallow: true },
    )
  }

  if (!ready || !accessToken) return null

  return (
    <>
      <Head>
        <title>{activeDoc ? `${activeDoc.title} · ${APP_NAME}` : APP_NAME}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="description" content="Real-time collaborative document editing" />
      </Head>

      <div className="layout">
        {/* ── Header ── */}
        <header className="app-header">
          <div className="app-header__brand">
            <svg className="app-header__logo" viewBox="0 0 32 32" fill="none">
              <rect width="32" height="32" rx="8" fill="#2563eb"/>
              <path d="M9 10h9M9 15h13M9 20h7" stroke="#fff" strokeWidth="2.2" strokeLinecap="round"/>
              <circle cx="24" cy="22" r="4" fill="#60a5fa"/>
              <path d="M23 22h2M24 21v2" stroke="#fff" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            <div>
              <span className="app-header__name">{APP_NAME}</span>
              <span className="app-header__tagline">{APP_TAGLINE}</span>
            </div>
          </div>

          {activeDoc && (
            <div className="app-header__doc-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              <span>{activeDoc.title}</span>
            </div>
          )}

          <div className="app-header__user">
            <div className="app-header__avatar">{email?.[0]?.toUpperCase()}</div>
            <span className="app-header__email">{email}</span>
            <button className="app-header__signout" onClick={logout}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
              Sign Out
            </button>
          </div>
        </header>

        {/* ── Body ── */}
        <div className="layout-body">
          <Sidebar
            activeDocId={activeDoc?.id ?? null}
            onSelect={doc => handleSelect(doc.id !== -1 ? doc : null)}
            onDocsLoaded={setAvailableDocs}
          />
          <main className="layout-main">
            {activeDoc ? (
              <Chat key={activeDoc.id} docId={activeDoc.id} docTitle={activeDoc.title} />
            ) : (
              <div className="empty-state">
                <div className="empty-state__inner">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#d1d5db" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="9" y1="13" x2="15" y2="13"/>
                    <line x1="9" y1="17" x2="13" y2="17"/>
                  </svg>
                  <p className="empty-state__title">No document open</p>
                  <p className="empty-state__sub">Select a document from the sidebar or create a new one</p>
                </div>
              </div>
            )}

            {/* ── Footer ── */}
            <footer className="app-footer">
              <span>© {new Date().getFullYear()} {APP_NAME} · {APP_TAGLINE}</span>
              <span className="app-footer__sep">·</span>
              <span>Built with Go, Django &amp; Next.js</span>
            </footer>
          </main>
        </div>
      </div>
    </>
  )
}
