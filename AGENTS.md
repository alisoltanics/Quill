# AGENTS.md

## Project Purpose

This is a **learning project** — a real-time collaborative document system built
to explore microservices architecture, system design, WebSocket patterns, and
AI-assisted development. It is not production software.

## Architecture Overview

```
┌─────────┐    WebSocket    ┌──────────┐    Redis Pub/Sub    ┌──────────┐
│ Frontend│◄───────────────►│ Gateway  │◄───────────────────►│ Gateway  │ (N instances)
│ Next.js │                 │ Go       │                     │ Go       │
└─────────┘                 └──────────┘                     └──────────┘
                                   │
                                   │ REST API
                                   ▼
                            ┌──────────────┐    Kafka     ┌──────────────┐
                            │ Document     │─────────────►│ Audit        │
                            │ Service      │              │ Service      │
                            │ Django + DRF │              │ Django       │
                            └──────────────┘              └──────────────┘
                                   │
                                   │ HTTP
                            ┌──────────────┐              ┌──────────────┐
                            │ Auth         │              │ Export       │
                            │ Service      │              │ Service      │
                            │ Django + DRF │              │ Django + DRF │
                            └──────────────┘              └──────────────┘
```

### Services

| Service | Stack | Port | Responsibility |
|---------|-------|------|----------------|
| `frontend` | Next.js, TipTap, Yjs | 3000 | Collaborative editor UI |
| `gateway` | Go, gorilla/websocket | 8080 | WebSocket connections, JWT auth, Redis pub/sub |
| `document-service` | Django, DRF, Yjs | 8000 | Document CRUD, CRDT merge, persistence |
| `auth-service` | Django, DRF | 8002 | JWT auth (register, login, refresh) |
| `audit-service` | Django, DRF | 8003 | Activity logging, Kafka consumer |
| `export-service` | Django, DRF | 8001 | PDF/HTML/Markdown export |
| `redis` | Redis 7 | 6379 | Pub/sub, presence, ephemeral state |
| `postgres` | PostgreSQL 15 | 5432 | Document storage |
| `audit-postgres` | PostgreSQL 15 | 5433 | Audit log storage |
| `kafka` | Kafka | 9092 | Event streaming for audit events |

## Tech Stack

- **Frontend**: Next.js, React, TipTap (ProseMirror), Yjs CRDT, Tailwind CSS
- **Gateway**: Go, gorilla/websocket, Redis pub/sub, JWT middleware
- **Services**: Python 3.11, Django, DRF, async SQLAlchemy (auth), sync SQLAlchemy (audit/export)
- **Data**: PostgreSQL 15, Redis 7, Kafka (KRaft mode)
- **Infra**: Docker Compose, Prometheus, Grafana, Jaeger

## Code Conventions

### Go (Gateway)

- Package-per-file: `main.go`, `hub.go`, `presence.go`, `config.go`
- Tests in same package (`_test.go` files in `services/gateway/`)
- Use `gorilla/websocket` for WebSocket, `go-redis` for Redis
- Channels + goroutines for concurrency, not shared state
- JWT secret read from env, no hardcoded secrets

### Python (Services)

- Each service has its own `Dockerfile` and `requirements.txt`
- DRF serializers in `api/serializers.py`, views in `api/views.py`
- Auth tests use `@patch` for `_JWT_SECRET` (module-level read)
- Audit/export `process_event` tests must patch `SessionLocal`
- pytest for Python tests, `pytest.ini` config per service
- All test files live in `services/<name>/tests/` or `services/<name>/api/tests/`

### Frontend

- TipTap + Yjs for collaborative editing
- `lib/yjsGateway.ts` — WebSocket ↔ Yjs sync
- `lib/api.ts` — REST API client with JWT
- `components/` — React components (Editor, ModeSwitch, SaveButton, etc.)
- Jest tests in `services/frontend/tests/`
- `jest.config.js` with `@edtr-io/ui` transform

### Databases

- Document Service → `postgres` (main DB)
- Auth Service → `postgres-auth` (own DB)
- Audit Service → `audit-postgres` (own DB)
- Each service owns its DB. No cross-service DB access.

## Testing

### Running All Tests

```bash
./services/scripts/run_all_tests.sh
```

### Per-Service

```bash
# Gateway (Go) — via Docker
docker compose build gateway && docker compose run --rm gateway go test -v ./...

# Auth Service (pytest)
docker compose build auth-service && docker compose run --rm auth-service pytest -v

# Audit Service (pytest)
docker compose build audit-service && docker compose run --rm audit-service pytest -v

# Export Service (pytest)
docker compose build export-service && docker compose run --rm export-service pytest -v

# Document Service (Django test)
docker compose build document-service && docker compose run --rm document-service python manage.py test api -v 2

# Frontend (Jest)
cd services/frontend && npx jest --forceExit --detectOpenHandles
```

### Test Counts (verified passing)

| Service | Framework | Tests |
|---------|-----------|-------|
| Gateway (Go) | go test | 57 |
| Auth Service | pytest | 19 |
| Audit Service | pytest | 13 |
| Export Service | pytest | 21 |
| Document Service | Django | 71 |
| Frontend | Jest | 15 |
| **Total** | | **196** |

## Common Pitfalls

### Go Tests

- `_JWT_SECRET` in Go is a `string`. Access it via exported `VerifyAccessToken`/`ExtractToken` functions.
- `hub_test.go` must stay in `services/gateway/` (Go requires test files in same package).
- `TestServerCORS` in `server_test.go` must use `t.Parallel()` or isolation issues.

### Circuit Breaker

- The gateway wraps reverse proxies with `circuitBreakerHandler` to fail fast when downstream services are down.
- Circuit state transitions are tracked via `gateway_circuit_breaker_transitions_total` metric.
- Rejected requests are counted via `gateway_circuit_breaker_rejections_total` metric.
- Default thresholds: 5 failures to open, 2 successes to close, 10s open timeout.

### CQRS

- Document service uses CQRS: `commands.py` for writes, `queries.py` for reads.
- `UNSET` sentinel in `commands.py` distinguishes "not provided" from `None`.
- Views are thin HTTP layer that delegates to commands/queries.

### Python Tests (Auth/Audit/Export)

- `_JWT_SECRET` is read at module import time. `override_settings` won't work. Use `@patch(f"{MODULE}._JWT_SECRET", JWT_SECRET)`.
- `process_event` uses its own `SessionLocal()`. Must `@patch("app.main.SessionLocal", TestingSessionLocal)`.
- DRF `IsAuthenticated` returns **403** (not 401) when no auth is provided. Returns **401** only on invalid token (`AuthenticationFailed`).
- DRF `CharField` has `trim_whitespace=True` by default. Use `trim_whitespace=False` on content fields.

### Yjs / Remote Cursors

- Yjs `Collaboration` extension replaces entire document content in transactions.
- `DecorationSet.map` drops all decorations. Must rebuild from stored cursor data on every transaction.
- Use `padding: 2px` wrapper (not CSS `:before` pseudo-element) for cursor decoration positioning.
- Debounce cursor broadcasts (~30ms).

### WebSocket / Redis Pub/Sub

- Gateway instances sync via Redis pub/sub (`doc:{docId}:events`, `doc:{docId}:presence`).
- Presence uses Redis sorted sets with 90s TTL (`doc:{docId}:online`).
- `broadcastPresence` runs periodically via goroutine ticker (10s).

## File Organization

```
├── AGENTS.md                          # This file
├── docker-compose.yml                 # All services orchestration
├── docs/
│   ├── system-implementation-guide.html      # Farsi architecture guide
│   ├── system-implementation-guide-en.html   # English architecture guide
│   ├── system-implementation-guide.md        # English markdown guide
│   ├── system-implementation-guide-fa.md     # Farsi markdown guide
│   └── dev-setup-and-run.md
├── services/
│   ├── gateway/                       # Go WebSocket gateway
│   │   ├── main.go, hub.go, presence.go, config.go, metrics.go, server.go, jwt.go
│   │   ├── circuit_breaker.go          # Circuit breaker pattern implementation
│   │   ├── *_test.go                  # 57 Go tests
│   │   └── Dockerfile (with test target)
│   ├── frontend/                      # Next.js collaborative editor
│   │   ├── components/, lib/, contexts/
│   │   ├── tests/                     # Jest tests
│   │   └── jest.config.js
│   ├── document_service/              # Django document CRUD + CRDT
│   │   ├── api/views.py, serializers.py, urls.py
│   │   ├── api/commands.py, queries.py # CQRS: write/read separation
│   │   └── tests/test_api.py          # 71 Django tests
│   ├── auth_service/                  # Django JWT auth
│   │   ├── app/main.py
│   │   └── tests/test_auth.py         # 19 pytest tests
│   ├── audit_service/                 # Django activity logging
│   │   ├── app/main.py
│   │   └── tests/test_audit.py        # 13 pytest tests
│   ├── export_service/                # Django PDF/HTML/MD export
│   │   ├── app/main.py
│   │   └── tests/test_export.py       # 21 pytest tests
│   └── scripts/
│       └── run_all_tests.sh           # Unified test runner
```

## How AI Agents Should Use This File

1. **Read this first** before making any changes.
2. **Check test counts** before and after modifications — all 177 tests must pass.
3. **Follow conventions** above for the language/service you're editing.
4. **Never commit secrets.** JWT secrets come from env vars.
5. **Use existing patterns** — check neighboring files before introducing new ones.
6. **Explain trade-offs** when suggesting architectural changes.
7. **Run `./services/scripts/run_all_tests.sh`** before finishing any task.
