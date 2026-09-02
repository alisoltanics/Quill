# Quill — Feature Overview & Roadmap Ideas

> A living document describing what **Quill** currently supports and a curated
> list of features you could add next. This is a **learning-oriented** roadmap —
> everything below is chosen to deepen your understanding of microservices,
> real-time collaboration, event-driven patterns, and system design.

---

## 1. Current Feature Set

### Real-Time Collaborative Editing
- TipTap (ProseMirror) editor wired to **Yjs CRDT** via the `Collaboration` extension.
- WebSocket gateway (Go) relays edits across **N gateway instances** using Redis Pub/Sub.
- Document content persisted as both HTML and a Yjs binary state (`yjs_state`).
- Debounced save (250ms) triggered on local document updates.

### Presence & Cursors
- Online user presence via Redis sorted sets with 90s TTL, synced through pub/sub.
- Live "N online" indicator with a dropdown of `onlineUsers`.
- Remote cursor decorations with per-user deterministic colors, plus cursor-name
  labels on hover.
- Presence heartbeat broadcast every 10s (gateway ticker).

### Roles & Permissions
- Full ACL model: `owner`, `editor`, `viewer` (enforced via backend and UI).
- **Share modal** to invite collaborators by email and set a role.
- Update / revoke permissions; "Shared with me" section in the sidebar shows
  docs others shared with you and the granted role.
- Viewers see a read-only editor; edit controls are hidden.

### Document & Folder Management (Sidebar)
- Create, rename, delete documents.
- Create, rename, delete folders; move docs into folders.
- Root-level docs and folder-organized docs; "Shared with me" grouping.
- Selecting a document loads and opens it in the editor.

### Diagram Editor (bonus)
- A React Flow diagram canvas alongside the write mode.
- Editable shape node types (rectangle, square, rounded, circle, colored boxes).
- Drag-to-connect edges with arrow markers, double-click to edit labels,
  delete key to remove selection.
- Persists diagram state to **localStorage** (per-doc).

### Export Service
- Export the active document as **Text (.txt)**, **Markdown (.md)**, or **HTML (.html)**.
- Triggered from the editor toolbar; downloads a file client-side.

### Auth & Account
- JWT-based register / login / refresh via the Auth Service.
- Access token forwarded on REST calls and on the WebSocket connection.

### Audit & Observability
- **Audit Service** consumes events from Kafka and logs timestamped activity.
- Prometheus / Grafana / Jaeger for metrics, dashboards, and tracing.

### Architecture Highlights (great learning examples)
- Gateway is stateless and scales horizontally; state lives in Redis.
- Each backend service owns its own PostgreSQL database (no cross-service DB calls).
- Async event flow: Gateway → Redis Pub/Sub for live sync, Service → Kafka for audit.
- Hot-reload for all source-mounted services; gateway rebuilds as a Go binary.

---

## 2. Feature Ideas (grouped by theme)

### A. Real-Time Editing — deepen the core
1. **Commenting & annotations** — users select text and add inline threaded comments
   (a classic collaborative feature and a great way to exercise ProseMirror selection
   + a new microservice or persisted store).
2. **Rich media** — image upload (drag-and-drop), embed YouTube / maps / code Playground.
3. **@-mentions with autocomplete** — mention collaborators; combines presence data
   with editor extensions.
4. **Slash commands** — type `/` to insert headings, tables, callouts, etc.
5. **Task lists / checkboxes** — collaborative to-do lists.
6. **Tables** — collaborative table support.
7. **Math / LaTeX** — inline math rendering (KaTeX).
8. **Real-time diagram collaboration** — currently diagrams only persist to
   localStorage; wire them into Yjs so multiple users can edit the same diagram live.
9. **Per-paragraph presence** — show who is editing which paragraph/block, not just a cursor.
10. **Offline editing & reconnect merge** — local Yjs buffer that syncs on reconnect.

> **Suggested learning focus:** #1 (comments) and #8 (collab diagrams) give the
> best bang for the buck — they reuse existing infra and introduce new
> architectural pieces naturally.

### B. Versioning, History & Recovery
1. **Revision history** — snapshot doc state; view + restore previous versions
   (you already store `yjs_state` periodically; layer a version endpoint on top).
2. **Soft-delete / trash** — deleted docs go to a trash bin with restore.
3. **Autosave indicator** — explicit "saved / saving / unsaved" UI state with timestamps.
4. **Multi-branch / fork** — copy a doc to a new one (cheap + useful).

### C. Search & Navigation
1. **Full-text search** across your documents and folders.
2. **Recent / starred docs** — pin frequently used documents.
3. **Quick switcher** — Cmd/Ctrl+K to jump to any doc/folder.
4. **Outline / table of contents** — auto-generated from headings.

### D. Sharing & Collaboration Tools
1. **Public share links** — view-only (or edit) links that don't require an account.
2. **Email invites** — actually send invite emails (uses a mail service / API).
3. **Activity feed** — "X edited this doc" / "Y commented" via the audit service.
4. **Real-time notifications** — toast/websocket push when someone comments or shares.

### E. Data, Export & Interop
1. **Google-Docs-style import** — paste/paste from Word with clean normalization.
2. **More export formats** — PDF (you have HTML; wire a headless-chrome/weasyprint path),
   DOCX.
3. **ZIP export** of a folder / multiple docs.
4. **Print-friendly view** — a clean read-only layout for printing.

### F. Observability & Operations
1. **Audit query UI** — browse the audit log via the frontend instead of only Kafka.
2. **Rate limiting & quotas** — per-user document/permission limits.
3. **Health endpoints + readiness probes** per service.
4. **Migrate Kafka to a transactional/outbox pattern** — the classic
   transactional-outbox for reliable event publishing.
5. **Idempotency keys** on writes to make the API resilient to retries.

### G. Performance & Scalability
1. **Redis caching** for hot documents (reduce DB load).
2. **Connection coalescing** — one WS per tab vs. multiple.
3. **Smarter sync** — send only deltas over the wire instead of full updates.
4. **Load testing** with k6/locust on the gateway; tune pub/sub fan-out.

### H. DX & AI Integration (the readme mentions AI)
1. **AI assist** — a "writing assistant" endpoint (summarize, rewrite, translate).
2. **AI chat** — retrieve context from the doc and answer questions about it.
3. **Auto-tagging / summarization** of new documents.

---

## 3. Suggested Priority Order

A good learning progression that builds on what exists and touches different layers:

| Phase | Focus | Features |
|-------|-------|----------|
| **P1 — Core UX** | Editing depth | Revision history, comments, @-mentions, tables |
| **P2 — Collaboration depth** | Real-time data | Collaborative diagrams (Yjs), per-block presence, offline buffer |
| **P3 — Discovery** | Search | Full-text search, recent/starred, quick switcher, TOC |
| **P4 — Sharing** | Access | Public links, activity feed, notifications |
| **P5 — Reliability** | Ops | Transactional outbox, idempotency, audit UI |
| **P6 — AI** | Intelligence | AI writing assistant & chat |

---

## 4. Quick Wins (shortest path)

If you want fast, high-value additions with minimal new infrastructure:

- **Revision history** (reuse existing `yjs_state` snapshots).
- **Starred / recent docs** (pure frontend + small backend list endpoint).
- **Task list extension** (add `@tiptap/extension-task-list` + a backend-safe schema).
- **Table extension** (`@tiptap/extension-table`, `table-row`, `table-cell`).
- **Print / PDF** (reuse your export service with an HTML-to-PDF path).
- **Collaborative diagrams** (inject diagram state into the Yjs document).

---

_This document is a living roadmap — update "Current Feature Set" as features land
and pick new items from the ideas list._
